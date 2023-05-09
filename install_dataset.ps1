param()
$EpName = [string]::new([System.Convert]::FromBase64String("cWVuZHBvaW50"))

New-Item -ItemType Directory -Force "Execution/benchmark_data/custom_ep/$EpName/hdt-store/"
Move-Item -Force dataset.hdt "Execution/benchmark_data/custom_ep/$EpName/hdt-store/index_dev.hdt"
Move-Item -Force dataset.hdt.index.v1-1 "Execution/benchmark_data/custom_ep/$EpName/hdt-store/index_dev.hdt.index.v1-1"