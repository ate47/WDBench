## Data loading

For double blind reason, we encoded the endpoint name into base 64 in the install scripts, if you really need it, you can it online [here](https://www.base64decode.org/).

Download the WDBench dataset [here](https://github.com/MillenniumDB/WDBench), index it using the latest version of the [HDT CLI](https://github.com/rdfhdt/hdt-java/releases/latest/download/rdfhdt.tar.gz) with this command.

For Windows user, use **rdf2hdt.ps1** instead of **rdf2hdt.sh**

```bash
rdf2hdt.sh -index dataset.nt dataset.hdt -multithread -config hdtopt.spec
```

put the result `dataset.hdt` and `dataset.index.v1-1` files in the root of the repository and run `./install_dataset.sh` (or `./install_dataset.ps1` on Windows), it will create the right directory and install the dataset in the Execution directory. You need to have the base64 command on Linux.

