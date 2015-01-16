# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Runs mesh network benchmarks.

Runs TCP_RR, TCP_STREAM benchmarks from netperf and compute total throughput
and average latency inside mesh network.
"""


import logging
import re
import threading

from perfkitbenchmarker import flags
from perfkitbenchmarker import vm_util


flags.DEFINE_integer('num_connections', 1,
                     'Number of connections between each pair of vms.')

flags.DEFINE_integer('num_iterations', 1,
                     'Number of iterations for each run.')


FLAGS = flags.FLAGS

BENCHMARK_INFO = {'name': 'mesh_benchmark',
                  'description': 'Get VM to VM cross section bandwidth for '
                                 'mesh network.',
                  'scratch_disk': False,
                  'num_machines': None}  # Set in GetInfo()

NETPERF_NAME = 'netperf-2.6.0.tar.gz'
NETPERF_LOC = 'ftp://ftp.netperf.org/netperf/%s' % NETPERF_NAME
NETPERF_BENCHMARKSS = ['TCP_RR', 'TCP_STREAM']
VALUE_INDEX = 1
RESULT_LOCK = threading.Lock()


def GetInfo():
  BENCHMARK_INFO['num_machines'] = FLAGS.num_vms
  if FLAGS.num_vms < 2:  # Needs at least 2 vms to run the benchmark.
    BENCHMARK_INFO['num_machines'] = 2
  return BENCHMARK_INFO


def PrepareVM(vm):
  """Prepare netperf on a single VM.

  Args:
    vm: The VM that needs to install netperf package.
  """
  logging.info('netperf prepare on %s', vm)
  vm.InstallPackage('build-essential')
  vm.RemoteCommand('tar xvfz %s' % NETPERF_NAME)
  make_cmd = 'cd netperf-2.6.0;./configure;make;sudo make install'
  vm.RemoteCommand(make_cmd)
  vm.RemoteCommand('netserver')


def Prepare(benchmark_spec):
  """Install vms with necessary softwares.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the banchmark.
  """
  vms = benchmark_spec.vms
  logging.info('downloading wget on %s', vms[0])
  wget_cmd = '/usr/bin/wget %s' % NETPERF_LOC
  vms[0].RemoteCommand(wget_cmd)
  for vm in vms:
    vms[0].MoveFile(vm, NETPERF_NAME)
  vm_util.RunThreaded(PrepareVM, vms, benchmark_spec.num_vms)


def RunNetperf(vm, benchmark_name, servers, result):
  """Spawns netperf on a remote VM, parses results.

  Args:
    vm: The VM running netperf.
    benchmark_name: The netperf benchmark to run.
    servers: VMs running netserver.
    result: The result variable shared by all threads.
  """
  cmd = ''
  if FLAGS.duration_in_seconds:
    cmd_duration_suffix = '-l %s' % FLAGS.duration_in_seconds
  else:
    cmd_duration_suffix = ''
  for server in servers:
    if vm != server:
      cmd += ('/usr/local/bin/netperf -t '
              '{benchmark_name} -H {server_ip} -i {iterations} '
              '{cmd_suffix} & ').format(
                  benchmark_name=benchmark_name,
                  server_ip=server.internal_ip,
                  iterations=FLAGS.num_iterations,
                  cmd_suffix=cmd_duration_suffix)
  netperf_cmd = ''
  for _ in range(FLAGS.num_connections):
    netperf_cmd += cmd
  netperf_cmd += 'wait'
  output, _ = vm.RemoteCommand(netperf_cmd)
  logging.info(output)

  match = re.findall(r'(\d+\.\d+)\s+\n', output)
  value = 0
  for res in match:
    if benchmark_name == 'TCP_RR':
      value += 1.0 / float(res) * 1000.0
    else:
      value += float(res)
  with RESULT_LOCK:
    result[VALUE_INDEX] += value


def Run(benchmark_spec):
  """Run netperf on target vms.

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.

  Returns:
    Total throughput, average latency in the form of tuple. The tuple contains
        the sample metric (string), value (float), unit (string).
  """
  vms = benchmark_spec.vms
  results = []
  for netperf_benchmark in NETPERF_BENCHMARKSS:
    args = []
    metadata = {
        'number_machines': benchmark_spec.num_vms,
        'number_connections': FLAGS.num_connections
    }

    if netperf_benchmark == 'TCP_STREAM':
      metric = 'TCP_STREAM_Total_Throughput'
      unit = 'Mbits/sec'
      value = 0.0
    else:
      metric = 'TCP_RR_Average_Latency'
      unit = 'ms'
      value = 0.0
    result = [metric, value, unit, metadata]
    args = [((source, netperf_benchmark, vms, result), {}) for source in vms]
    vm_util.RunThreaded(RunNetperf, args, benchmark_spec.num_vms)
    if netperf_benchmark == 'TCP_RR':
      result[VALUE_INDEX] /= ((benchmark_spec.num_vms - 1) *
                              benchmark_spec.num_vms *
                              FLAGS.num_connections)
    results.append(result)
  print results
  return results


def Cleanup(benchmark_spec):
  """Cleanup netperf on the target vm (by uninstalling).

  Args:
    benchmark_spec: The benchmark specification. Contains all data that is
        required to run the benchmark.
  """
  vms = benchmark_spec.vms
  for vm in vms:
    logging.info('uninstalling netperf on %s', vm)
    vm.RemoteCommand('pkill -9 netserver')
    make_cmd = 'cd netperf-2.6.0;sudo make uninstall'
    vm.RemoteCommand(make_cmd)
    vm.RemoteCommand('rm -rf netperf-2.6.0')
    vm.RemoteCommand('rm -f %s' % NETPERF_NAME)
    vm.UninstallPackage('build-essential')