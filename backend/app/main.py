import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
import pika
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .consumer import consumer
from .events import events
from .effects import read_effects
from .experiments import experiment
from .messaging import connection, declare, publish


@asynccontextmanager
async def lifespan(app):
    if not settings.lab_token or not settings.rabbit_password:
        raise RuntimeError("LAB_TOKEN과 RABBIT_PASSWORD를 설정하세요. scripts/init_env.py를 실행할 수 있습니다.")
    yield
    consumer.shutdown()
    experiment.shutdown()


app = FastAPI(title="MessageFlow Lab · Phase 0–2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Lab-Token"])


def authorize(x_lab_token: str = Header(default="")):
    if not settings.lab_token or not secrets.compare_digest(x_lab_token.encode(), settings.lab_token.encode()):
        raise HTTPException(status_code=401, detail="실습 토큰이 일치하지 않습니다.")


class PublishRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4096)
    count: int = Field(default=1, ge=1, le=3)


class AckRequest(BaseModel):
    attempt_id: str = Field(min_length=1, max_length=100)


@app.exception_handler(pika.exceptions.AMQPError)
async def broker_error(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": "RabbitMQ 연결 오류입니다. 일부 발행이 전송됐을 수 있으므로 재시도 전에 기록과 Queue를 확인하세요."})


def queue_stats(queue=None):
    queue = queue or settings.queue
    with connection() as conn:
        declare(conn.channel(), queue)
    url = f"{settings.management_url.rstrip('/')}/api/queues/{quote(settings.rabbit_vhost, safe='')}/{quote(queue, safe='')}"
    try:
        with httpx.Client(timeout=4, trust_env=False) as client:
            # A newly declared queue can exist before Management has sampled
            # its first gauges. Wait briefly; never substitute zero values.
            for sample in range(6):
                response = client.get(url, auth=(settings.rabbit_user, settings.rabbit_password))
                response.raise_for_status()
                data = response.json()
                if all(key in data for key in ("name", "messages_ready", "messages_unacknowledged", "consumers")):
                    break
                if sample < 5:
                    time.sleep(0.3)
        # Missing/stale metrics must not be manufactured as zero.
        return {"name": data["name"], "ready": data["messages_ready"], "unacked": data["messages_unacknowledged"], "consumers": data["consumers"]}
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="Queue 지표를 아직 수집하지 못했습니다. 잠시 후 다시 연결하세요.") from exc


@app.get("/health")
def health():
    return {"status": "api-running", "phase": "0–2", "broker_checked": False}


@app.get("/snapshot", dependencies=[Depends(authorize)])
def snapshot():
    stats = queue_stats()
    return {"queue": stats, **consumer.view(), **events.view(settings.queue), "collected_at": datetime.now(timezone.utc).isoformat()}


@app.get("/rabbit/queues", dependencies=[Depends(authorize)])
def queues():
    return [queue_stats()]


@app.get("/rabbit/messages", dependencies=[Depends(authorize)])
def messages():
    # Event history, not destructive broker message inspection.
    return events.view(settings.queue)


@app.post("/rabbit/messages", dependencies=[Depends(authorize)])
def post_message(request: PublishRequest):
    if not request.body.strip():
        raise HTTPException(status_code=422, detail="빈 메시지는 발행할 수 없습니다.")
    return publish(request.body, request.count)


@app.post("/consumer/start", dependencies=[Depends(authorize)])
def start_consumer():
    try:
        return consumer.start()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/consumer/ack", dependencies=[Depends(authorize)])
def ack(request: AckRequest):
    try:
        return consumer.command("ack", request.attempt_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="ACK를 확인할 수 없습니다. 재시도 전에 현재 전달 상태를 확인하세요.") from exc


@app.post("/consumer/stop", dependencies=[Depends(authorize)])
def stop_consumer():
    try:
        result = consumer.command("stop")
        consumer.shutdown()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail="Consumer 종료 상태를 확인하세요.") from exc


class ExperimentPublishRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4096)


class ExperimentControlRequest(BaseModel):
    attempt_id: str | None = Field(default=None, min_length=1, max_length=100)


@app.get("/experiments/snapshot", dependencies=[Depends(authorize)])
def experiment_snapshot():
    return {"queue": queue_stats(settings.experiment_queue), **experiment.view(),
            **events.view(settings.experiment_queue), **read_effects(),
            "collected_at": datetime.now(timezone.utc).isoformat()}


@app.post("/experiments/messages", dependencies=[Depends(authorize)])
def experiment_publish(request: ExperimentPublishRequest):
    if not request.body.strip():
        raise HTTPException(422, "빈 메시지는 발행할 수 없습니다.")
    return publish(request.body, 1, settings.experiment_queue)


@app.post("/experiments/start", dependencies=[Depends(authorize)])
def experiment_start():
    try:
        return experiment.start()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/experiments/{action}", dependencies=[Depends(authorize)])
def experiment_control(action: str, request: ExperimentControlRequest | None = None):
    if action not in {"process", "ack", "crash", "stop"}:
        raise HTTPException(404, "허용되지 않은 실험 동작입니다.")
    if action in {"process", "ack"} and (request is None or request.attempt_id is None):
        raise HTTPException(422, "현재 처리 시도 ID가 필요합니다.")
    try:
        if action == "crash":
            return experiment.crash()
        result = experiment.command(action, request.attempt_id if request else None)
        if action == "stop":
            experiment.shutdown()
        return result
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(503, "실험 동작 결과를 확인하지 못했습니다. 이력과 현재 전달 상태를 확인하세요.") from exc
