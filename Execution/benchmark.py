from SPARQLWrapper import SPARQLWrapper, JSON
from socket import timeout
import multiprocessing
import os
import re
import subprocess
import sys
import time
import traceback
import pathlib
import psutil

# Usage:
# python benchmark.py <ENGINE> <QUERIES_FILE> <LIMIT> <PREFIX_NAME>
# LIMIT = 0 will not add a limit

# Db engine that will execute queries
ENGINE       = sys.argv[1]
QUERIES_FILE = os.path.abspath(sys.argv[2])
LIMIT        = sys.argv[3]
PREFIX_NAME  = sys.argv[4]

###################### EDIT THIS PARAMETERS ######################
TIMEOUT = 60 # Max time per query in seconds
BENCHMARK_ROOT = 'C:\\Users\\wilat\\workspace\\WDBench\\Execution\\benchmark_data'

# Path to needed output and input files
RESUME_FILE = f'{BENCHMARK_ROOT}/results/{PREFIX_NAME}_{ENGINE}_limit_{LIMIT}.csv'
ERROR_FILE  = f'{BENCHMARK_ROOT}/results/errors/{PREFIX_NAME}_{ENGINE}_limit_{LIMIT}.log'

SERVER_LOG_FILE  = f'{BENCHMARK_ROOT}/scripts/log/{PREFIX_NAME}_{ENGINE}_limit_{LIMIT}.log'

VIRTUOSO_LOCK_FILE = f'{BENCHMARK_ROOT}/virtuoso/wikidata/virtuoso.lck'

# use absolute paths to avoid problems with current directory
ENGINES_PATHS = {
    'BLAZEGRAPH': f'{BENCHMARK_ROOT}/blazegraph/service',
    'JENA':       f'{BENCHMARK_ROOT}/jena',
    'VIRTUOSO':   f'{BENCHMARK_ROOT}/virtuoso',
    'QLEVER':     f'{BENCHMARK_ROOT}/qlever',
    'QENDPOINT':  f'{BENCHMARK_ROOT}/qendpoint',
}

ENGINES_PORTS = {
    'BLAZEGRAPH': 9999,
    'JENA':       3030,
    'VIRTUOSO':   1111,
    'QLEVER':     7001,
    'QENDPOINT':  1234,
}

ENDPOINTS = {
    'BLAZEGRAPH': 'http://localhost:9999/bigdata/namespace/wdq/sparql',
    'JENA':       'http://localhost:3030/jena/sparql',
    'VIRTUOSO':   'http://localhost:8890/sparql',
    'QLEVER':     'http://localhost:7001/sparql',
    'QENDPOINT':  'http://localhost:1234/api/endpoint/sparql',
}

SERVER_CMD = {
    'BLAZEGRAPH': ['./runBlazegraph.sh'],
    'JENA': f'java -Xmx64g -jar apache-jena-fuseki-4.1.0/fuseki-server.jar --loc=apache-jena-4.1.0/wikidata --timeout={TIMEOUT*1000} /jena'.split(' '),
    'VIRTUOSO': ['bin/virtuoso-t', '-c', 'wikidata.ini', '+foreground'],
    'QLEVER': f'TIMEOUT=600; PORT=7001; docker run --rm -v $QLEVER_HOME/qlever-indices/wikidata:/index  -p $PORT:7001 -e INDEX_PREFIX=wikidata --name qlever.wikidata qlever-docker',
    'QENDPOINT':  ['java', '-jar', 'qendpoint.jar'],
}
#######################################################

PORT = ENGINES_PORTS[ENGINE]

# ================== Auxiliars ===============================
def lsof(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False
        for conn in proc.connections():
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port == PORT:
                return True
    except psutil.NoSuchProcess:
        pass # ignore nsp
    return False

def lsofany() -> bool:
    for conn in psutil.net_connections():
        if conn.status == psutil.CONN_LISTEN and conn.laddr.port == PORT:
            return True
        
    return False

# ================== Parsers =================================
def parse_to_sparql(query):
    if not LIMIT:
        return f'SELECT * WHERE {{ {query} }}'
    return f'SELECT * WHERE {{ {query} }} LIMIT {LIMIT}'


def IRI_to_mdb(iri):
    expressions = []

    # property
    expressions.append(re.compile(r"^<http://www\.wikidata\.org/prop/direct/([QqPp]\d+)>$"))

    # entity
    expressions.append(re.compile(r"^<http://www\.wikidata\.org/entity/([QqPp]\d+)>$"))

    # string
    expressions.append(re.compile(r'^("(?:[^"\\]|\\.)*")$'))

    # something with schema
    expressions.append(re.compile(r'^("(?:[^"\\]|\\.)*")\^\^<http://www\.w3\.org/2001/XMLSchema#\w+>$'))

    # string with idiom
    expressions.append(re.compile(r'^"((?:[^"\\]|\\.)*)"@(.+)$'))

    # point
    expressions.append(re.compile(r'^"((?:[^"\\]|\\.)*)"\^\^<http://www\.opengis\.net/ont/geosparql#wktLiteral>$'))

    # anon
    expressions.append(re.compile(r'^_:\w+$'))

    # math
    expressions.append(re.compile(r'^"((?:[^"\\]|\\.)*)"\^\^<http://www\.w3\.org/1998/Math/MathML>$'))

    for expression in expressions:
        match_iri = expression.match(iri)
        if match_iri is not None:
            return match_iri.groups()[0]


    # other url
    other_expression = re.compile(r"^<(.+)>$")
    match_iri = other_expression.match(iri)
    if match_iri is not None:
        return f'"{match_iri.groups()[0]}"'
    else:
        raise Exception(f'unhandled iri: {iri}')


def start_server():
    global server_process
    os.chdir(ENGINES_PATHS[ENGINE])
    print('starting server...')

    server_log.write("[start server]\n")
    server_process = subprocess.Popen(SERVER_CMD[ENGINE], stdout=server_log, stderr=server_log)
    print(f'pid: {server_process.pid}')

    # Sleep to wait server start
    while not lsof(server_process.pid):
        time.sleep(1)

    print(f'done')


def kill_server():
    global server_process
    print(f'killing server[{server_process.pid}]...')
    server_log.write("[kill server]\n")
    if ENGINE == 'VIRTUOSO':
        kill_process = subprocess.Popen([f'{ENGINES_PATHS[ENGINE]}/bin/isql', f'localhost:{PORT}', '-K'])
        kill_process.wait()
    else:
        server_process.kill()
        server_process.wait()

    while lsof(server_process.pid):
        time.sleep(1)

    if ENGINE == 'VIRTUOSO':
        kill_process = subprocess.Popen(['rm', VIRTUOSO_LOCK_FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        kill_process.wait()
    print('done')


# Send query to server
def execute_queries():
    with open(QUERIES_FILE) as queries_file:
        for line in queries_file:
            query_number, query = line.split(',')
            print(f'Executing query {query_number}')
            query_sparql(query, query_number)


def execute_sparql_wrapper(query_pattern, query_number):
    query = parse_to_sparql(query_pattern)

    sparql_wrapper = SPARQLWrapper(ENDPOINTS[ENGINE])
    # sparql_wrapper.setTimeout(TIMEOUT+10) # Give 10 more seconds for a chance to graceful timeout
    sparql_wrapper.setReturnFormat(JSON)
    sparql_wrapper.setQuery(query)

    count = 0
    start_time = time.time()

    try:
        # Compute query
        results = sparql_wrapper.query()
        json_results = results.convert()
        for _ in json_results["results"]["bindings"]:
            count += 1

        elapsed_time = int((time.time() - start_time) * 1000) # Truncate to milliseconds

        with open(RESUME_FILE, 'a') as file:
            file.write(f'{query_number},{count},OK,{elapsed_time}\n')

    except Exception as e:
        elapsed_time = int((time.time() - start_time) * 1000) # Truncate to milliseconds
        with open(RESUME_FILE, 'a') as file:
            file.write(f'{query_number},,ERROR({type(e).__name__}),{elapsed_time}\n')

        with open(ERROR_FILE, 'a') as file:
            file.write(f'Exception in query {str(query_number)} [{type(e).__name__}]: {str(e)}\n')


def query_sparql(query_pattern, query_number):
    start_time = time.time()

    try:
        p = multiprocessing.Process(target=execute_sparql_wrapper, args=[query_pattern, query_number])
        p.start()
        # Give 2 more seconds for a chance to graceful timeout or enumerate the results
        p.join(TIMEOUT + 2)
        if p.is_alive():
            p.kill()
            p.join()
            raise Exception("PROCESS_TIMEOUT")

    except Exception as e:
        elapsed_time = int((time.time() - start_time) * 1000) # Truncate to milliseconds
        with open(RESUME_FILE, 'a') as file:
            file.write(f'{query_number},,TIMEOUT({type(e).__name__}),{elapsed_time}\n')

        with open(ERROR_FILE, 'a') as file:
            file.write(f'Exception in query {str(query_number)} [{type(e).__name__}]: {str(e)}\n')

        kill_server()
        start_server()


def main():
    global server_log
    os.makedirs(pathlib.Path(SERVER_LOG_FILE).absolute().parent, exist_ok=True)

    with open(SERVER_LOG_FILE, 'w') as server_log:
        server_process = None

        # Check if output file already exists
        if os.path.exists(RESUME_FILE):
            resumte_file_bkp = RESUME_FILE + ".bck"
            idx = 0
            while os.path.exists(resumte_file_bkp):
                idx += 1
                resumte_file_bkp = RESUME_FILE + "_" + str(idx) + ".bck"
            os.rename(RESUME_FILE, resumte_file_bkp)
            print(f'File "{RESUME_FILE}" already exists, creating backup at "{resumte_file_bkp}".')
            
        os.makedirs(pathlib.Path(RESUME_FILE).absolute().parent, exist_ok=True)
        os.makedirs(pathlib.Path(ERROR_FILE).absolute().parent, exist_ok=True)

        with open(RESUME_FILE, 'w') as file:
            file.write('query_number,results,status,time\n')

        with open(ERROR_FILE, 'w') as file:
            file.write('') # to replaces the old error file

        if lsofany():
            raise Exception("other server already running")

        print('benchmark is starting. TIMEOUT', TIMEOUT, 'seconds')
        start_server()
        execute_queries()

        if server_process is not None:
            kill_server()


if __name__== "__main__":
    main()