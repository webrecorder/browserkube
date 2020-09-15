#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

mkdir -p docs
mkdir -p docs/charts
cd $DIR/docs/charts

helm package $DIR/chart
helm repo index . --url https://webrecorder.github.io/browserkube/charts


