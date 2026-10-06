"""Publish directly through Pika without FastAPI. Run from API container."""
import argparse
import json

from app.messaging import publish

parser = argparse.ArgumentParser()
parser.add_argument("body", nargs="?", default="hello")
parser.add_argument("--count", type=int, default=3, choices=range(1, 4))
args = parser.parse_args()
print(json.dumps(publish(args.body, args.count), ensure_ascii=False))
