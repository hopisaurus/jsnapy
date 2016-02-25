#!/usr/bin/python
import sys
import os
import textwrap
import argparse
import yaml
from jnpr.jsnapy.snap import Parser
from jnpr.jsnapy.check import Comparator
from jnpr.jsnapy.notify import Notification
from threading import Thread
from jnpr.junos import Device
from jnpr.jsnapy import version
import colorama
import getpass
import Queue
import logging
import setup_logging
from jnpr.jsnapy import get_path
from jnpr.jsnapy.testop import Operator
from jnpr.junos.exception import ConnectAuthError

logging.getLogger("paramiko").setLevel(logging.WARNING)


class SnapAdmin:

    # need to call this function to initialize logging
    setup_logging.setup_logging()

    def __init__(self):
        """
        taking parameters from command line
        """
        colorama.init(autoreset=True)
        self.q = Queue.Queue()
        self.log_detail = {'hostname': None}
        self.snap_del = False
        self.logger = logging.getLogger(__name__)
        self.parser = argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            description=textwrap.dedent('''\
                                        Tool to capture snapshots and compare them
                                        It supports five subcommands:
                                         --snap, --check, --snapcheck, --diff
                                        1. Take snapshot:
                                                jsnapy --snap pre_snapfile -f main_configfile
                                        2. Compare snapshots:
                                                jsnapy --check post_snapfile pre_snapfile -f main_configfile
                                        3. Compare current configuration:
                                                jsnapy --snapcheck snapfile -f main_configfile
                                        4. Take diff without specifying test case:
                                                jsnapy --diff pre_snapfile post_snapfile -f main_configfile
                                            '''),
            usage="\n This tool enables you to capture and audit runtime environment snapshots of your "
            "networked devices running the Junos operating system (Junos OS)\n")

        group = self.parser.add_mutually_exclusive_group()
        # for mutually exclusive gp, can not use two or more options at a time
        group.add_argument(
            '--snap',
            action='store_true',
            help="take the snapshot for commands specified in test file")
        group.add_argument(
            '--check',
            action='store_true',
            help=" compare pre and post snapshots based on test operators specified in test file")
        group.add_argument(
            '--snapcheck',
            action='store_true',
            help='check current snapshot based on test file')

      #########
      # will supoort it later
      # for windows
      ########
      #  group.add_argument(
      #      "--init",
      #      action="store_true",
      #      help="generate init folders: snapshots, configs and main.yml",
      #  )
      #########

        group.add_argument(
            "--diff",
            action="store_true",
            help="display difference between two snapshots"
        )
        group.add_argument(
            "--version",
            action="store_true",
            help="displays version"
        )

        self.parser.add_argument(
            "pre_snapfile",
            nargs='?',
            help="pre snapshot filename")       # make it optional
        self.parser.add_argument(
            "post_snapfile",
            nargs='?',
            help="post snapshot filename",
            type=str)       # make it optional
        self.parser.add_argument(
            "-f", "--file",
            help="config file to take snapshot",
            type=str)
        self.parser.add_argument("-t", "--hostname", help="hostname", type=str)
        self.parser.add_argument(
            "-p",
            "--passwd",
            help="password to login",
            type=str)
        self.parser.add_argument(
            "-l",
            "--login",
            help="username to login",
            type=str)
       # self.parser.add_argument(
       #     "-m",
       #     "--mail",
       #     help="mail result to given id",
       #     type=str)
        # self.parser.add_argument(
        #    "-o",
        #    "--overwrite",
        #    action='store_true',
        #    help="overwrite directories and files generated by init",
        #)

        self.args = self.parser.parse_args()

        self.db = dict()
        self.db['store_in_sqlite'] = False
        self.db['check_from_sqlite'] = False
        self.db['db_name'] = ""
        self.db['first_snap_id'] = None
        self.db['second_snap_id'] = None

    def get_version(self):
        """
        This function gives version of Jsnapy
        :return: return JSNAPy version
        """
        return version.__version__

    '''
    def generate_init(self):
       """
       # generate init folder, will support it later
        create snapshots and configs folder along with sample main config file.
        All snapshots generated will go in snapshots folder. configs folder will contain
        all the yaml file apart from main, like device.yml, bgp_neighbor.yml
        :return:
       """

        mssg = "Creating Jsnapy directory structure at: ", os.getcwd()
        self.logger.debug(colorama.Fore.BLUE + mssg)
        if not os.path.isdir("snapshots"):
            os.mkdir("snapshots")
        dst_config_path = os.path.join(os.getcwd(), 'configs')
         overwrite files if given option -o or --overwrite
        if not os.path.isdir(dst_config_path) or self.args.overwrite is True:
            distutils.dir_util.copy_tree(os.path.join(os.path.dirname(__file__), 'configs'),
                                         dst_config_path)
        dst_main_yml = os.path.join(dst_config_path, 'main.yml')
        if not os.path.isfile(
                os.path.join(os.getcwd(), 'main.yml')) or self.args.overwrite is True:
            shutil.copy(dst_main_yml, os.getcwd())

        logging_yml_file = os.path.join(
            os.path.dirname(__file__),
            'logging.yml')
        if not os.path.isfile(
                os.path.join(os.getcwd(), 'logging.yml')) or self.args.overwrite is True:
            shutil.copy(logging_yml_file, os.getcwd())
        mssg1= "Successfully created Jsnap directories at:",os.getcwd()
        self.logger.info(colorama.Fore.BLUE + mssg1)
    '''

    def chk_database(self, config_file, pre_snapfile,
                     post_snapfile, check=None, snap=None, action=None):
        """
        This function test parameters for sqlite and then update database accordingly
        :param config_file: main config file
        :param pre_snapfile: pre snapshot file
        :param post_snapfile: post snapshot file
        :param check: True if --check operator is given
        :param snap:
        :param action: used by module version, either snap, check or snapcheck
        """
        d = config_file['sqlite'][0]
        compare_from_id = False
        if d.__contains__('store_in_sqlite'):
            self.db['store_in_sqlite'] = d['store_in_sqlite']
        if d.__contains__('check_from_sqlite'):
            self.db['check_from_sqlite'] = d['check_from_sqlite']

        if (self.db['store_in_sqlite']) or (self.db['check_from_sqlite']):
                                            # and (check is True or action is
                                            # "check")):
            if d.__contains__('database_name'):
                self.db['db_name'] = d['database_name']

            else:
                self.logger.error(
                    colorama.Fore.RED +
                    "Specify name of the database.",
                    extra=self.log_detail)
                exit(1)
            if check is True or self.args.diff is True or action is "check":
                if 'compare' in d.keys() and d['compare'] is not None:
                    strr = d['compare']
                    if not isinstance(strr, str):
                        self.logger.error(colorama.Fore.RED + "Properly specify ids of first and "
                                                              "second snapshot in format: first_snapshot_id, second_snapshot_id", extra=self.log_detail)
                        exit(1)
                    compare_from_id = True
                    lst = [val.strip() for val in strr.split(',')]
                    try:
                        lst = [int(x) for x in lst]
                    except ValueError as ex:
                        self.logger.error(colorama.Fore.RED + "Properly specify id numbers of first and second snapshots"
                                          " in format: first_snapshot_id, second_snapshot_id", extra=self.log_detail)
                        #raise Exception(ex)
                        exit(1)
                    if len(lst) > 2:
                        self.logger.error(colorama.Fore.RED + "No. of snapshots specified is more than two."
                                          " Please specify only two snapshots.", extra=self.log_detail)
                        exit(1)
                    if len(lst) == 2 and isinstance(
                            lst[0], int) and isinstance(lst[1], int):
                        self.db['first_snap_id'] = lst[0]
                        self.db['second_snap_id'] = lst[1]
                    else:
                        self.logger.error(colorama.Fore.RED + "Properly specify id numbers of first and second snapshots"
                                          " in format: first_snapshot_id, second_snapshot_id", extra=self.log_detail)
                        exit(1)
        if self.db['check_from_sqlite'] is False or compare_from_id is False:
            if (check is True and (pre_snapfile is None or post_snapfile is None) or
                    self.args.diff is True and (pre_snapfile is None or post_snapfile is None)):
                self.logger.debug(
                    colorama.Fore.RED +
                    "Arguments not given correctly, Please refer below help message", extra=self.log_detail)
                self.parser.print_help()
                sys.exit(1)

    def get_hosts(self):
        """
        Called by main function, it extracts main config file and also check for database
        Reads the yaml config file given by user and pass the extracted data to login function to
        read device details and connect them. Also checks sqlite key to check if user wants to
        create database for snapshots
        """
        if self.args.pre_snapfile is not None:
            output_file = self.args.pre_snapfile
        elif self.args.snapcheck is True and self.args.pre_snapfile is None:
            output_file = "snap_temp"
            self.snap_del = True
        else:
            output_file = ""
        conf_file = self.args.file
        check = self.args.check
        snap = self.args.snap
        if os.path.isfile(conf_file):
            config_file = open(conf_file, 'r')
            self.main_file = yaml.load(config_file)
        elif os.path.isfile(os.path.join(get_path('DEFAULT', 'config_file_path'), conf_file)):
            fpath = get_path('DEFAULT', 'config_file_path')
            config_file = open(os.path.join(fpath, conf_file), 'r')
            self.main_file = yaml.load(config_file)
        else:
            self.logger.error(
                colorama.Fore.RED +
                "ERROR!! file path '%s' for main config file is not correct" %
                conf_file, extra=self.log_detail)
            sys.exit(1)

        if self.main_file.__contains__(
                'sqlite') and self.main_file['sqlite'] and self.main_file['sqlite'][0]:
            self.chk_database(
                self.main_file,
                self.args.pre_snapfile,
                self.args.post_snapfile,
                check,
                snap)
        else:
            if (self.args.check is True and (
                    self.args.file is None or self.args.pre_snapfile is None or self.args.post_snapfile is None)):
                self.logger.error(
                    "Arguments not given correctly, Please refer help message",
                    extra=self.log_detail)
                self.parser.print_help()
                sys.exit(1)
        self.login(output_file)

    def generate_rpc_reply(self, dev, output_file, hostname, config_data):
        """
        Generates rpc-reply based on command/rpc given and stores them in snap_files
        :param dev: device handler
        :param output_file: filename to store snapshots
        :param hostname: hostname of device
        :param config_data : data of main config file
        """
        test_files = []
        for tfile in config_data.get('tests'):
            if not os.path.isfile(tfile):
                tfile = os.path.join(
                    get_path(
                        'DEFAULT',
                        'test_file_path'),
                    tfile)
            if os.path.isfile(tfile):
                test_file = open(tfile, 'r')
                test_files.append(yaml.load(test_file))
            else:
                self.logger.error(
                    colorama.Fore.RED +
                    "ERROR!! File %s is not found for taking snapshots" %
                    tfile, extra=self.log_detail)

        g = Parser()
        for tests in test_files:
            g.generate_reply(tests, dev, output_file, hostname, self.db)

    def compare_tests(
            self, hostname, config_data, pre_snap=None, post_snap=None, action=None):
        """
        called by check and snapcheck argument, to compare snap files
        calls the function to compare snapshots based on arguments given
        (--check, --snapcheck, --diff)
        :param hostname: device name
        :return: return object of Operator containing test details
        """
        comp = Comparator()
        chk = self.args.check
        diff = self.args.diff
        pre_snap_file = self.args.pre_snapfile if pre_snap is None else pre_snap
        if (chk or diff or action in ["check", "diff"]):
            post_snap_file = self.args.post_snapfile if post_snap is None else post_snap
            test_obj = comp.generate_test_files(
                config_data,
                hostname,
                chk,
                diff,
                self.db,
                self.snap_del,
                pre_snap_file,
                action,
                post_snap_file)
        else:
            test_obj = comp.generate_test_files(
                config_data,
                hostname,
                chk,
                diff,
                self.db,
                self.snap_del,
                pre_snap_file,
                action)
        return test_obj

    def login(self, output_file):
        """
        Extract device information from main config file. Stores device information and call connect function,
        device can be single or multiple. Instead of connecting to all devices mentioned in yaml file, user can
        connect to some particular group of devices also.
        :param output_file: name of snapshot file
        """
        self.host_list = []
        if self.args.hostname is None:
            try:
                k = self.main_file['hosts'][0]
            except KeyError as ex:
                self.logger.error(
                    "\nERROR occurred !! Hostname not given properly %s" %
                    str(ex),
                    extra=self.log_detail)
                #raise Exception(ex)
            except Exception as ex:
                self.logger.error(
                    "\nERROR occurred !! %s" %
                    str(ex),
                    extra=self.log_detail)
                #raise Exception(ex)
            else:
                # when group of devices are given, searching for include keyword in
                # hosts in main.yaml file
                if k.__contains__('include'):
                    file_tag = k['include']
                    if os.path.isfile(file_tag):
                        lfile = file_tag
                    else:
                        lfile = os.path.join(
                            get_path(
                                'DEFAULT',
                                'test_file_path'),
                            file_tag)
                    login_file = open(lfile, 'r')
                    dev_file = yaml.load(login_file)
                    gp = k.get('group', 'all')

                    dgroup = [i.strip().lower() for i in gp.split(',')]
                    for dgp in dev_file:
                        if dgroup[0].lower() == 'all' or dgp.lower() in dgroup:
                            for val in dev_file[dgp]:
                                hostname = val.keys()[0]
                                self.log_detail = {'hostname': hostname}
                                self.host_list.append(hostname)
                                if val.get(hostname) is not None and 'username' in val.get(
                                        hostname).keys():
                                    username = val.get(
                                        hostname).get('username')
                                else:
                                    username = self.args.login if self.args.login is not None else raw_input(
                                        "\nEnter User name: ")
                                if val.get(hostname) is not None and 'passwd' in val.get(
                                        hostname).keys():
                                    password = val.get(hostname).get('passwd')
                                else:
                                    password = self.args.passwd
                                    # if self.args.passwd is not None else
                                    # getpass.getpass("\nEnter Password for
                                    # username: %s " %username)
                                t = Thread(
                                    target=self.connect,
                                    args=(
                                        hostname,
                                        username,
                                        password,
                                        output_file,
                                    ))
                                t.start()
                                t.join()
            # login credentials are given in main config file, can connect to only
            # one device
                else:
                    try:
                        hostname = k['devices']
                        self.log_detail = {'hostname': hostname}
                    except KeyError as ex:
                        self.logger.error(
                            colorama.Fore.RED +
                            "ERROR!! KeyError 'devices' key not found",
                            extra=self.log_detail)
                        #raise Exception(ex)
                    except Exception as ex:
                        self.logger.error(
                            colorama.Fore.RED +
                            "ERROR!! %s" %
                            ex,
                            extra=self.log_detail)
                        #raise Exception(ex)
                    else:
                        username = k.get('username') or self.args.login or raw_input(
                            "\nEnter User name: ")
                        password = k.get('passwd') or self.args.passwd
                        self.host_list.append(hostname)
                        self.connect(hostname, username, password, output_file)

        # login credentials are given from command line
        else:
            hostname = self.args.hostname
            self.log_detail = {'hostname': hostname}
            username = self.args.login if self.args.login is not None else raw_input(
                "\nEnter User name: ")
            password = self.args.passwd
            # if self.args.passwd is not None else getpass.getpass("\nEnter
            # Password: ")
            self.host_list.append(hostname)
            self.connect(hostname, username, password, output_file)

    def get_test(self, config_data, hostname, snap_file, post_snap, action):
        """
        Analyse testfile and return object of testop.Operator containing test details
        called by connect() function and other functions of Jsnapy module functions
        :param config_data: data of main config file
        :param hostname: hostname
        :param snap_file: pre snapshot file name
        :param post_snap: post snapshot file name
        :param action: action to be taken (check, snapcheck, snap)
        :return: object of testop.Operator containing test details
        """
        res = Operator()
        if config_data.get("mail") and self.args.diff is not True:
            mfile = os.path.join(get_path('DEFAULT', 'test_file_path'), config_data.get('mail'))\
                if os.path.isfile(config_data.get('mail')) is False else config_data.get('mail')
            if os.path.isfile(mfile):
                mail_file = open(mfile, 'r')
                mail_file = yaml.load(mail_file)
                if "passwd" not in mail_file:
                    passwd = getpass.getpass(
                        "Please enter ur email password ")
                else:
                    passwd = mail_file['passwd']
                res = self.compare_tests(
                    hostname,
                    config_data,
                    snap_file,
                    post_snap,
                    action)
                send_mail = Notification()
                send_mail.notify(mail_file, hostname, passwd, res)
            else:
                self.logger.error(
                    colorama.Fore.RED +
                    "ERROR!! Path of file containing mail content is not correct", extra=self.log_detail)
        else:
            res = self.compare_tests(
                hostname,
                config_data,
                snap_file,
                post_snap,
                action)

        self.q.put(res)
        return res

    def connect(self, hostname, username, password, output_file,
                config_data=None, action=None, post_snap=None):
        """
        connect to device and calls the function either to generate snapshots
        or compare them based on option given (--snap, --check, --snapcheck, --diff)
        :param hostname: ip/ hostname of device
        :param username: username of device
        :param password: password to connect to device
        :param snap_files: file name to store snapshot
        :return: if snap operation is performed then return true on success
                 if snapcheck or check operation is performed then return test details
        """
        res = False
        if config_data is None:
            config_data = self.main_file

        if self.args.snap is True or self.args.snapcheck is True or action in [
                "snap", "snapcheck"]:
            self.logger.info(
                colorama.Fore.BLUE +
                "Connecting to device %s ................", hostname, extra=self.log_detail)
            dev = Device(
                host=hostname,
                user=username,
                passwd=password,
                gather_facts=False)
            try:
                dev.open()
            except ConnectAuthError as ex:
                if password is None and action is None:
                    password = getpass.getpass(
                        "\nEnter Password for username: %s" %
                        username)
                    self.connect(
                        hostname,
                        username,
                        password,
                        output_file,
                        config_data,
                        action,
                        post_snap)
                else:
                    self.logger.error(
                        "\nERROR occurred %s" %
                        str(ex),
                        extra=self.log_detail)
                    raise Exception(ex)
            except Exception as ex:
                self.logger.error(
                    "\nERROR occurred %s" %
                    str(ex),
                    extra=self.log_detail)
                raise Exception(ex)
            else:
                self.generate_rpc_reply(
                    dev,
                    output_file,
                    hostname,
                    config_data)
                dev.close()
                res = True

        if self.args.check is True or self.args.snapcheck is True or self.args.diff is True or action in [
                "check", "snapcheck"]:
            res = self.get_test(
                config_data,
                hostname,
                output_file,
                post_snap,
                action)
        return res

    ############################### functions to support module ##############

    def multiple_device_details(
            self, host, config_data, pre_name, action, post_name):
        """
        Called when multiple devices are given in config file
        :param host: hostname
        :param config_data: data of main config file
        :param pre_name: pre snapshot filename or file tag
        :param action: action to be taken, snap, snapcheck, check
        :param post_name: post snapshot filename or file tag
        :return: return object of testop.Operator containing test details
        """
        res_obj = []
        self.host_list = []
        login_file = host['include']
        login_file = login_file if os.path.isfile(
            host.get('include')) else os.path.join(
            get_path(
                'DEFAULT',
                'test_file_path'),
            login_file)
        login_file = open(login_file, 'r')
        dev_file = yaml.load(login_file)
        gp = host.get('group', 'all')
        dgroup = [i.strip().lower() for i in gp.split(',')]
        for dgp in dev_file:
            if dgroup[0].lower() == 'all' or dgp.lower() in dgroup:
                for val in dev_file[dgp]:
                    hostname = val.keys()[0]
                    self.host_list.append(hostname)
                    self.log_detail['hostname'] = hostname
                    username = val.get(hostname).get('username')
                    password = val.get(hostname).get('passwd')
                    t = Thread(
                        target=self.connect,
                        args=(
                            hostname,
                            username,
                            password,
                            pre_name,
                            config_data,
                            action,
                            post_name))
                    t.start()
                    if action in ["snapcheck", "check"]:
                        res_obj.append(self.q.get())
                    else:
                        res_obj.append(True)
                    t.join()
        return res_obj

    def extract_data(
            self, config_data, pre_name=None, action=None, post_name=None):
        """
        Called when dev= None, i.e. device details are passed inside config file
        It parse details of main config file and call functions to connect to device
        and take snapshots
        :param config_data: data of main config file
        :param pre_name: pre snapshot filename or file tag
        :param action: action to be taken, snap, snapcheck, check
        :param post_name: post snapshot filename or file tag
        :return: return object of testop.Operator containing test details
        """
        res_obj = []

        if os.path.isfile(config_data):
            data = open(config_data, 'r')
            config_data = yaml.load(data)
        elif isinstance(config_data, str):
            config_data = yaml.load(config_data)
        else:
            self.logger.info(
                colorama.Fore.RED +
                "incorrect config file or data, please chk !!!!", extra=self.log_detail)
            exit(1)
        try:
            host = config_data.get('hosts')[0]
        except Exception as ex:
            self.logger.error(
                colorama.Fore.RED +
                "ERROR!! config file not defined properly, %s" %
                ex,
                extra=self.log_detail)
            raise Exception("config file not defined properly", ex)
        else:
            if config_data.__contains__(
                    'sqlite') and config_data['sqlite'] and config_data['sqlite'][0]:
                self.chk_database(
                    config_data,
                    pre_name,
                    post_name,
                    None,
                    None,
                    action)
            if host.__contains__('include'):
                res_obj = self.multiple_device_details(
                    host,
                    config_data,
                    pre_name,
                    action,
                    post_name)
            else:
                hostname = host.get('devices')
                self.log_detail = {'hostname': hostname}
                username = host.get('username')
                password = host.get('passwd')
                #pre_name = hostname + '_' + pre_name if not os.path.isfile(pre_name) else pre_name
                # if action is "check":
                #    post_name= hostname + '_' + post_name if not os.path.isfile(post_name) else post_name
                val = self.connect(
                    hostname,
                    username,
                    password,
                    pre_name,
                    config_data,
                    action,
                    post_name)
                res_obj.append(val)
            return res_obj

    def extract_dev_data(
            self, dev, config_data, pre_name=None, action=None, post_snap=None):
        """
        Used to parse details given in main config file, when device object is passed in function
        :param dev: Device object
        :param config_data: data of main config file
        :param pre_name: pre snapshot filename or file tag
        :param action: action to be taken, snap, check or snapcheck
        :param post_snap: post snapshot filename or file tag
        :return: return object of testop.Operator containing test details
        """
        res = []
        if os.path.isfile(config_data):
            data = open(config_data, 'r')
            config_data = yaml.load(data)
        elif isinstance(config_data, str):
            config_data = yaml.load(config_data)
        else:
            self.logger.info(
                colorama.Fore.RED +
                "incorrect config file or data, please chk !!!!", extra=self.log_detail)
            exit(1)
        try:
            hostname = dev.hostname
            self.log_detail = {'hostname': hostname}
        except Exception as ex:
            self.logger.error(
                colorama.Fore.RED +
                "ERROR!! message is: %s" %
                ex,
                extra=self.log_detail)
            raise Exception(ex)
        else:
            if config_data.__contains__(
                    'sqlite') and config_data['sqlite'] and config_data['sqlite'][0]:
                self.chk_database(
                    config_data,
                    pre_name,
                    post_snap,
                    None,
                    None,
                    action)

            if action in ["snap", "snapcheck"]:
                try:
                    self.generate_rpc_reply(
                        dev,
                        pre_name,
                        hostname,
                        config_data)
                except Exception as ex:
                    self.logger.error(
                        "\nERROR occurred %s" %
                        str(ex),
                        extra=self.log_detail)
                else:
                    res = True
            if action in ["snapcheck", "check"]:
                res = []
                res.append(
                    self.get_test(
                        config_data,
                        hostname,
                        pre_name,
                        post_snap,
                        action))
            return res

    def snap(self, data, file_name, dev=None):
        """
        Function equivalent to --snap operator, for module version
        :param data: either main config file or string containing details of main config file
        :param file_name: snap file, either complete filename or file tag
        :param dev: device object
        """
        if isinstance(dev, Device):
            res = self.extract_dev_data(dev, data, file_name, "snap")
        else:
            res = self.extract_data(data, file_name, "snap")
        return res

    def snapcheck(self, data, file_name=None, dev=None):
        """
        Function equivalent to --snapcheck operator, for module version
        :param data: either main config file or string containing details of main config file
        :param pre_file: pre snap file, either complete filename or file tag
        :param dev: device object
        :return: return object of testop.Operator containing test details
        """
        if file_name is None:
            file_name = "snap_temp"
            self.snap_del = True
        if isinstance(dev, Device):
            res = self.extract_dev_data(dev, data, file_name, "snapcheck")
        else:
            res = self.extract_data(data, file_name, "snapcheck")
        return res

    def check(self, data, pre_file=None, post_file=None, dev=None):
        """
        Function equivalent to --check operator, for module version
        :param data: either main config file or string containing details of main config file
        :param pre_file: pre snap file, either complete filename or file tag
        :param post_file: post snap file, either complete filename or file tag
        :param dev: device object
        :return: return object of testop.Operator containing test details
        """
        if isinstance(dev, Device):
            res = self.extract_dev_data(
                dev,
                data,
                pre_file,
                "check",
                post_file)
        else:
            res = self.extract_data(data, pre_file, "check", post_file)
        return res

    #######  generate init folder ######
    '''
    def generate_init(self):

        create snapshots and configs folder along with sample main config file.
        All snapshots generated will go in snapshots folder. configs folder will contain
        all the yaml file apart from main, like device.yml, bgp_neighbor.yml
        :return:

        mssg= "Creating Jsnapy directory structure at:" + os.getcwd()
        self.logger.debug(colorama.Fore.BLUE + mssg)
        if not os.path.isdir("snapshots"):
            os.mkdir("snapshots")
        if not os.path.isdir("logs"):
            os.mkdir("logs")
        dst_config_path = os.path.join(os.getcwd(), 'configs')
        # overwrite files if given option -o or --overwrite
        if not os.path.isdir(dst_config_path) or self.args.overwrite is True:
            distutils.dir_util.copy_tree(os.path.join(os.path.dirname(__file__), 'configs'),
                                         dst_config_path)
        dst_main_yml = os.path.join(dst_config_path, 'main.yml')
        if not os.path.isfile(
                os.path.join(os.getcwd(), 'main.yml')) or self.args.overwrite is True:
            shutil.copy(dst_main_yml, os.getcwd())

        logging_yml_file = os.path.join(
            os.path.dirname(__file__),
            'logging.yml')
        if not os.path.isfile(
                os.path.join(os.getcwd(), 'logging.yml')) or self.args.overwrite is True:
            shutil.copy(logging_yml_file, os.getcwd())
        mssg1= "Jsnap folders created at: " + os.getcwd()
        self.logger.info(colorama.Fore.BLUE + mssg1)
    '''

    def check_arguments(self):
        """
        checks combination of arguments given from command line and display help if correct
        set of combination is not given.
        :return: print message in command line, regarding correct usage of JSNAPy
        """
        if((self.args.snap is True and (self.args.pre_snapfile is None or self.args.file is None)) or
            (self.args.snapcheck is True and self.args.file is None) or
            (self.args.check is True and self.args.file is None)
           ):
            self.logger.error(
                "Arguments not given correctly, Please refer help message", extra=self.log_detail)
            self.parser.print_help()
            sys.exit(1)
        if self.args.diff is True:
            if (self.args.pre_snapfile is not None and os.path.isfile(self.args.pre_snapfile)) and (
                    self.args.post_snapfile is not None and os.path.isfile(self.args.post_snapfile)):
                comp = Comparator()
                comp.compare_diff(
                    self.args.pre_snapfile,
                    self.args.post_snapfile,
                    None)
                sys.exit(1)
            else:
                if self.args.file is None:
                    self.parser.print_help()
                    sys.exit(1)


def main():
    js = SnapAdmin()
    if len(sys.argv) == 1:
        js.parser.print_help()
        sys.exit(1)
    else:
        js.check_arguments()
        if js.args.version is True:
            print "Jsnapy version:", version.__version__
        else:
            js.get_hosts()

if __name__ == '__main__':
    main()