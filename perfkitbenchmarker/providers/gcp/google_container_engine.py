# Copyright 2017 PerfKitBenchmarker Authors. All rights reserved.
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

"""Contains classes/functions related to GKE (Google Container Engine)."""

import os

from perfkitbenchmarker import container_service
from perfkitbenchmarker import flags
from perfkitbenchmarker import providers
from perfkitbenchmarker import vm_util
from perfkitbenchmarker.providers.gcp import util

FLAGS = flags.FLAGS
_KUBERNETES_MASTER_VERSION = '1.6.2'


class GkeCluster(container_service.KubernetesCluster):

  CLOUD = providers.GCP

  def __init__(self, spec):
    super(GkeCluster, self).__init__(spec)
    self.name = 'pkb-%s' % FLAGS.run_uri
    self.project = spec.vm_spec.project

  def _Create(self):
    """Creates the cluster."""
    cmd = util.GcloudCommand(self, 'container', 'clusters', 'create', self.name)
    cmd.flags['num-nodes'] = self.num_nodes
    cmd.flags['machine-type'] = self.machine_type
    cmd.flags['cluster-version'] = _KUBERNETES_MASTER_VERSION
    cmd.Issue()

  def _PostCreate(self):
    """Acquire cluster authentication."""
    cmd = util.GcloudCommand(
        self, 'container', 'clusters', 'get-credentials', self.name)
    if not FLAGS.kubeconfig:
      FLAGS.kubeconfig = vm_util.PrependTempDir('kubeconfig')
    env = os.environ.copy()
    env['KUBECONFIG'] = FLAGS.kubeconfig
    cmd.Issue(env=env)

  def _Delete(self):
    """Deletes the cluster."""
    cmd = util.GcloudCommand(
        self, 'container', 'clusters', 'delete', self.name)
    cmd.Issue()

  def _Exists(self):
    """Returns True if the cluster exits."""
    cmd = util.GcloudCommand(
        self, 'container', 'clusters', 'describe', self.name)
    _, _, retcode = cmd.Issue(suppress_warning=True)
    return retcode == 0
