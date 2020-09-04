#!/bin/bash
DIR=$( dirname "${BASH_SOURCE[0]}" )
echo $DIR
docker build -t ikreymer/permaproof-main:dev $DIR

