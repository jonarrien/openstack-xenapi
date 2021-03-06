#!/usr/bin/env python
# Copyright (c) 2012 OpenStack Foundation
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

# NOTE: XenServer still only supports Python 2.4 in it's dom0 userspace
# which means the Nova xenapi plugins must use only Python 2.4 features

from distutils.version import StrictVersion
import logging
import os
import re
import time

import dom0_pluginlib as pluginlib
import utils

pluginlib.configure_logging("disk_utils")


def wait_for_dev(session, dev_path, max_seconds):
    for i in range(0, max_seconds):
        if os.path.exists(dev_path):
            return dev_path
        time.sleep(1)

    return ""


def _get_sfdisk_version():
    out = utils.run_command(['/sbin/sfdisk', '-v'])
    if out:
        # Return the first two numbers from the version.
        # In XS6.5, it's 2.13-pre7. Just return 2.13 for this case.
        pattern = re.compile("(\d+)\.(\d+)")
        match = pattern.search(out.split('\n')[0])
        if match:
            return match.group(0)


def make_partition(session, dev, partition_start, partition_end):
    # Since XS7.0 which has sfdisk V2.23, we observe sfdisk has a bug
    # that sfdisk will wrongly calculate cylinders when specify Sector
    # as unit (-uS). That bug will cause the partition operation failed.
    # And that's fixed in 2.26. So as a workaround, let's use the option
    # of '--force' for version <=2.25 and >=2.23. '--force' will ignore
    # the wrong cylinder value but works as expected.
    VER_FORCE_MIN = '2.23'
    VER_FORCE_MAX = '2.25'
    dev_path = utils.make_dev_path(dev)

    if partition_end != "-":
        raise pluginlib.PluginError("Can only create unbounded partitions")

    sfdisk_ver = _get_sfdisk_version()
    cmd_list = ['sfdisk', '-uS', dev_path]
    if sfdisk_ver:
        if StrictVersion(sfdisk_ver) >= StrictVersion(VER_FORCE_MIN) and \
           StrictVersion(sfdisk_ver) <= StrictVersion(VER_FORCE_MAX):
            cmd_list = ['sfdisk', '--force', '-uS', dev_path]

    utils.run_command(cmd_list, '%s,;\n' % (partition_start))


def _mkfs(fs, path, label):
    """Format a file or block device

    :param fs: Filesystem type (only 'swap', 'ext3' supported)
    :param path: Path to file or block device to format
    :param label: Volume label to use
    """
    if fs == 'swap':
        args = ['mkswap']
    elif fs == 'ext3':
        args = ['mkfs', '-t', fs]
        # add -F to force no interactive execute on non-block device.
        args.extend(['-F'])
        if label:
            args.extend(['-L', label])
    else:
        raise pluginlib.PluginError("Partition type %s not supported" % fs)
    args.append(path)
    utils.run_command(args)


def mkfs(session, dev, partnum, fs_type, fs_label):
    dev_path = utils.make_dev_path(dev)

    out = utils.run_command(['kpartx', '-avspp', dev_path])
    try:
        logging.info('kpartx output: %s' % out)
        mapperdir = os.path.join('/dev', 'mapper')
        dev_base = os.path.basename(dev)
        partition_path = os.path.join(mapperdir, "%sp%s" % (dev_base, partnum))
        _mkfs(fs_type, partition_path, fs_label)
    finally:
        # Always remove partitions otherwise we can't unplug the VBD
        utils.run_command(['kpartx', '-dvspp', dev_path])

if __name__ == "__main__":
    utils.register_plugin_calls(wait_for_dev,
                                make_partition,
                                mkfs)
