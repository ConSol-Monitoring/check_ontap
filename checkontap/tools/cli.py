#    Copyright (C) 2023  ConSol Consulting & Solutions Software GmbH
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.


import argparse
import getpass
import os
import signal
from checkontap import CheckOntapTimeout

__author__ = "ConSol"

def timeout_handler(signum, frame):
    raise CheckOntapTimeout("Timeout reached")

def set_timeout(seconds=None, handler=None):
    if seconds is None:
        seconds = int(os.environ.get("TIMEOUT", "30"))
    signal.signal(signal.SIGALRM, (handler or timeout_handler))
    signal.alarm(seconds)
    
class EnvDefault(argparse.Action):
    def __init__(self, envvar, required=True, default=None, **kwargs):
        if not default and envvar:
            if os.environ.get(envvar, None):
                default = os.environ[envvar]
        if required and default:
            required = False
        super(EnvDefault, self).__init__(default=default, required=required, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)

class Parser:
    """
    Samples specific argument parser.
    Wraps argparse to ease the setup of argument requirements for the samples.

    Example:
        parser = cli.Parser()
        parser.add_required_arguments(cli.Argument.WARNING)
        parser.add_optional_arguments(cli.Argument.CLUSTER_NAME, cli.Argument.NIC_NAME)
        parser.add_custom_argument(
            '--disk-number', required=True, help='Disk number to change mode.')
        args = parser.get_args()
    """

    def __init__(self):
        """
        Defines two arguments groups.
        One for the standard arguments and one for sample specific arguments.
        The standard group cannot be extended.
        """
        self._parser = argparse.ArgumentParser(description='check_ontap',
                                               formatter_class=argparse.RawTextHelpFormatter,
                                               conflict_handler='resolve',
                                               )
        self._standard_args_group = self._parser.add_argument_group('standard arguments')
        self._specific_args_group = self._parser.add_argument_group('sample-specific arguments')

        # because -h is reserved for 'help' we use -s for service
        self._standard_args_group.add_argument('-H', '--host',
                                               required=True,
                                               action='store',
                                               help='NetApp device service address to connect to')

        # because we want -p for password, we use -o for port
        self._standard_args_group.add_argument('-P', '--port',
                                               type=int,
                                               default=443,
                                               action='store',
                                               help='Port to connect on')

        self._standard_args_group.add_argument('-u', '--api_user',
                                               required=True,
                                               action='store',
                                               help='API User name to use when connecting to host')

        self._standard_args_group.add_argument('-p', '--api_pass',
                                               required=True,
                                               action=EnvDefault,
                                               envvar='NETAPP_API_PASS',
                                               help='Password to use when connecting to host, '
                                                    'can also be set by env NETAPP_API_PASS')


        self._standard_args_group.add_argument('-nossl', '--disable-ssl-verification',
                                               required=False,
                                               action='store_true',
                                               help='Disable ssl host certificate verification')

        self._standard_args_group.add_argument('--verbose', '-v',
                                                required=False,
                                                action='count',
                                                help='Verbose output')

    def get_args(self):
        """
        Supports the command-line arguments needed to form a connection to NetApp ONTAP.
        """
        args = self._parser.parse_args()
        x = self._parser.parse_known_args()
        return args

    def _add_sample_specific_arguments(self, is_required: bool, *args):
        """
        Add an argument to the "sample specific arguments" group
        Requires a predefined argument from the Argument class.
        """
        for arg in args:
            name_or_flags = arg["name_or_flags"]
            options = arg["options"]
            options["required"] = is_required
            self._specific_args_group.add_argument(*name_or_flags, **options)

    def add_required_arguments(self, *args):
        """
        Add a required argument to the "sample specific arguments" group
        Requires a predefined argument from the Argument class.
        """
        self._add_sample_specific_arguments(True, *args)

    def add_optional_arguments(self, *args):
        """
        Add an optional argument to the "sample specific arguments" group.
        Requires a predefined argument from the Argument class.
        """
        self._add_sample_specific_arguments(False, *args)

    def add_custom_argument(self, *name_or_flags, **options):
        """
        Uses ArgumentParser.add_argument() to add a full definition of a command line argument
        to the "sample specific arguments" group.
        https://docs.python.org/3/library/argparse.html#the-add-argument-method
        """
        self._specific_args_group.add_argument(*name_or_flags, **options)

    def set_epilog(self, epilog):
        """
        Text to display after the argument help
        """
        self._parser.epilog = epilog
        
    def set_description(self, description):
        """
        Text to display at the begining of the help page
        """
        self._parser.description = description

    def _prompt_for_password(self, args):
        """
        if no password is specified on the command line, prompt for it
        """
        if not args.password:
            args.password = getpass.getpass(
                prompt='"--password" not provided! Please enter password for host %s and user %s: '
                       % (args.host, args.user))
        return args


class Argument:
    """
    Predefined arguments to use in the Parser

    Example:
        parser = cli.Parser()
        parser.add_optional_arguments(cli.Argument.WARNING)
        parser.add_optional_arguments(cli.Argument.CLUSTER_NAME, cli.Argument.NIC_NAME)
    """
    def __init__(self):
        pass

    WARNING = {
        'name_or_flags': ['-w', '--warning'],
        'options': {'action': 'store', 'help': 'Warning threshold'}
    }
    CRITICAL = {
        'name_or_flags': ['-c', '--critical'],
        'options': {'action': 'store', 'help': 'Critical threshold'}
    }
    EXCLUDE = {
        'name_or_flags': ['--exclude'],
        'options': {'action': 'store', 'help': 'Excluding items'}
    }
    INCLUDE = {
        'name_or_flags': ['--include'],
        'options': {'action': 'store', 'help': 'Including items'}
    }
    UNIT = {
        'name_or_flags': ['-U', '--unit'],
        'options': {
            'action': 'store',
            'help': 'Unit to deal with',
            'choices': ['%', 'kB', 'MB', 'GB', 'TB', 'PB'],
        }
    }
    METRIC = {
        'name_or_flags': ['-m', '--metric'],
        'options': {
            'action': 'store',
            'default': 'usage',
            'choices': ['usage', 'free_kB', 'used_kB', 'free_MB', 'used_MB', 'free_GB', 'used_GB', 'free_TB', 'used_TB', 'free_PB', 'used_PB'],
            'help': 'The metric to apply the thresholds on, defaults to `usage`, can be: '
                    'usage (in percent), free and used. '
                    'free and used are measured in bytes. You can one of these suffixes: '
                    'kB, MB, GB for example: free_MB or used_GB'
        }
    }
    NAME = {
        'name_or_flags': ['--name'],
        'options': {
            'action': 'append',
            'nargs': '+',
            'help': 'define something',
        }
    }
    TYPE = {
        'name_or_flags': ['--type'],
        'options': {
            'action': 'store',
            'nargs': '+',
            'help': 'define something',
        }
    }
    PERFDATA = {
        'name_or_flags': ['--perfdata'],
        'options': {
            'action': 'store_true',
            'required': 'false',
            'help': 'add performance data to Output',
        }
    }
    INODE_WARN = {
        'name_or_flags': ['--inode-warning'],
        'options': {
            'action': 'store',
            'help': 'Inode warning threshold in percent'
        }
    }
    INODE_CRIT = {
        'name_or_flags': ['--inode-critical'],
        'options': {
            'action': 'store',
            'help': 'Inode critical threshold in percent'
        }
    }
    SNAP_WARN = {
        'name_or_flags': ['--snapshot-warning'],
        'options': {
            'action': 'store',
            'help': 'Snapshot used space warning threshold in percent'
        }
    }
    SNAP_CRIT = {
        'name_or_flags': ['--snapshot-critical'],
        'options': {
            'action': 'store',
            'help': 'Snapshot used space critical threshold in percent'
        }
    }