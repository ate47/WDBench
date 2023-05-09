#!/usr/bin/env bash
#/ double blind
EP_NAME=`echo "cWVuZHBvaW50Cg" | base64 --decode`

mkdir -p "Execution/benchmark_data/custom_ep/$EP_NAME/hdt-store/"
mv dataset.hdt "Execution/benchmark_data/custom_ep/$EP_NAME/hdt-store/index_dev.hdt"
mv dataset.hdt.index.v1-1 "Execution/benchmark_data/custom_ep/$EP_NAME/hdt-store/index_dev.hdt.index.v1-1"