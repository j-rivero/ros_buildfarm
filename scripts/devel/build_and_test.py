#!/usr/bin/env python3

# Copyright 2014, 2016 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os
import sys

from ros_buildfarm.argument import add_argument_build_tool
from ros_buildfarm.argument import add_argument_build_tool_args
from ros_buildfarm.argument import add_argument_require_gpu_support
from ros_buildfarm.common import has_gpu_support
from ros_buildfarm.common import Scope
from ros_buildfarm.workspace import call_build_tool
from ros_buildfarm.workspace import clean_workspace
from ros_buildfarm.workspace import ensure_workspace_exists


def main(argv=sys.argv[1:]):
    parser = argparse.ArgumentParser(
        description='Invoke the build tool on a workspace while enabling and '
                    'running the tests')
    parser.add_argument(
        '--rosdistro-name',
        required=True,
        help='The name of the ROS distro to identify the setup file to be '
             'sourced (if available)')
    add_argument_build_tool(parser, required=True)
    add_argument_build_tool_args(parser)
    parser.add_argument(
        '--workspace-root',
        required=True,
        help='The root path of the workspace to compile')
    parser.add_argument(
        '--parent-result-space', nargs='*',
        help='The paths of the parent result spaces')
    parser.add_argument(
        '--clean-before',
        action='store_true',
        help='The flag if the workspace should be cleaned before the '
             'invocation')
    parser.add_argument(
        '--clean-after',
        action='store_true',
        help='The flag if the workspace should be cleaned after the '
             'invocation')
    add_argument_require_gpu_support(parser)
    args = parser.parse_args(argv)

    ensure_workspace_exists(args.workspace_root)

    if args.clean_before:
        clean_workspace(args.workspace_root)

    parent_result_spaces = None
    if args.parent_result_space:
        parent_result_spaces = args.parent_result_space

    try:
        with Scope('SUBSECTION', 'build workspace in isolation'):
            test_results_dir = os.path.join(
                args.workspace_root, 'test_results')
            cmake_args = [
                '-DBUILD_TESTING=1',
                '-DCATKIN_ENABLE_TESTING=1', '-DCATKIN_SKIP_TESTING=0',
                '-DCATKIN_TEST_RESULTS_DIR=%s' % test_results_dir]
            # Check gpu support
            # No GPU support will exclude gpu_test tag by default
            ctest_args = ['-LE "gpu_test"']
            if args.require_gpu_support:
                if not has_gpu_support():
                    print("--require-gpu-support is enabled but can not detect nvidia support installed")
                    sys.exit(-1)
                if args.run_only_gpu_tests:
                    ctest_args = ['-L "gpu_test"']
                else:
                    # GPU support, run all tests
                    ctest_args = []
            additional_args = args.build_tool_args or []
            if args.build_tool == 'colcon':
                additional_args += ['--test-result-base', test_results_dir]
            env = dict(os.environ)
            env.setdefault('MAKEFLAGS', '-j1')
            rc = call_build_tool(
                args.build_tool, args.rosdistro_name, args.workspace_root,
                cmake_clean_cache=True,
                cmake_args=cmake_args, args=additional_args,
                ctest_args=None,
                parent_result_spaces=parent_result_spaces, env=env)
        if not rc:
            with Scope('SUBSECTION', 'build tests'):
                additional_args = args.build_tool_args or []
                if args.build_tool == 'colcon':
                    additional_args += ['--cmake-target-skip-unavailable']
                rc = call_build_tool(
                    args.build_tool, args.rosdistro_name, args.workspace_root,
                    cmake_args=cmake_args,
                    ctest_args=None,
                    make_args=['tests'], args=additional_args,
                    parent_result_spaces=parent_result_spaces, env=env)
            if not rc:
                make_args = ['run_tests']
                additional_args = args.build_tool_args or []
                if args.build_tool == 'colcon':
                    cmake_args = None
                    ctest_args = ctest_args
                    make_args = None
                    additional_args = ['--test-result-base', test_results_dir]
                # for workspaces with only plain cmake packages the setup files
                # generated by cmi won't implicitly source the underlays
                if parent_result_spaces is None:
                    parent_result_spaces = ['/opt/ros/%s' % args.rosdistro_name]
                if args.build_tool == 'catkin_make_isolated':
                    devel_space = os.path.join(
                        args.workspace_root, 'devel_isolated')
                    parent_result_spaces.append(devel_space)
                # since catkin_make_isolated doesn't provide a custom
                # environment to run tests this needs to source the devel space
                # and force a CMake run ro use the new environment
                with Scope('SUBSECTION', 'run tests'):
                    rc = call_build_tool(
                        args.build_tool,
                        args.rosdistro_name, args.workspace_root,
                        cmake_args=cmake_args,
                        ctest_args=ctest_args,
                        force_cmake=args.build_tool == 'catkin_make_isolated',
                        make_args=make_args, args=additional_args,
                        parent_result_spaces=parent_result_spaces, env=env,
                        colcon_verb='test')
    finally:
        if args.clean_after:
            clean_workspace(args.workspace_root)

    return rc


if __name__ == '__main__':
    sys.exit(main())
