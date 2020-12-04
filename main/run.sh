#!/bin/bash

uvicorn $APP_MODULE:app --port $PORT --host 0.0.0.0

