#   Copyright 2014-2015 PUNCH Cyber Analytics Group
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""
Overview
========

Process a payload using yara

"""

import os
import time
import argparse
import threading
import yara
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from stoq.args import StoqArgs
from stoq.plugins import StoqWorkerPlugin


class YaraScan(StoqWorkerPlugin, FileSystemEventHandler):

    def __init__(self):
        super().__init__()
        self.rule_lock = threading.Lock()
        self.wants_heartbeat = True

    def activate(self, stoq):

        self.stoq = stoq

        parser = argparse.ArgumentParser()
        parser = StoqArgs(parser)
        worker_opts = parser.add_argument_group("Plugin Options")
        worker_opts.add_argument("-r", "--yararules",
                                 dest='yararules',
                                 help="Path to yara rules file")

        options = parser.parse_args(self.stoq.argv[2:])

        super().activate(options=options)

        # Make sure we compile our rules when activated.
        self._load_yara_rules()

        return True

    def scan(self, payload, **kwargs):
        """
        Scan a payload using yara
        :param bytes payload: Payload to be scanned
        :param **kwargs yararules: specify a particular ruleset
        :returns: Results from scan
        :rtype: dict or None
        """

        # Define our required variables
        self.results = []

        # Scan the payload with a timeout using yara
        self.rule_lock.acquire()

        # We want to be special... let's use a specific ruleset
        if 'yararules' in kwargs:
            ruleset_path = kwargs.pop('yararules')
            self._custom_scan(payload, ruleset_path)

        else:
            self.rules.match(data=payload, timeout=60,
                             callback=self._scan_callback)

        self.rule_lock.release()
        super().scan()

        # Return our results
        if self.results:
            # Because we may have multiple yara rules hit, let's ensure we return a list of lists
            # with results, otherwise stoQ will save each yara rule as an individual scan, rather
            # than a collective of results from one payload.
            return [self.results]
        else:
            return None

    def _custom_scan(self, payload, ruleset):

        # StringIO Object
        if hasattr(ruleset, 'getvalue'):
            try:
                rules = yara.compile(source=ruleset.getvalue())
            except yara.Error:
                rules = None
                self.log.error("Unable to compile ruleset from passed StringIO object")

        # File path
        else:
            try:
                # Assume the target ruleset is already compiled
                rules = yara.load(filepath=ruleset)
            except yara.Error:
                # What?! These rules aren't compiled? Fine... let's try to compile them
                try:
                    rules = yara.compile(filepath=ruleset)
                except yara.Error:
                    # Well that was unfortunate, no rules for us
                    rules = None
                    self.log.error("Unable to load custom ruleset from filepath {}".format(ruleset))

        if rules:
            rules.match(data=payload, timeout=60,
                        callback=self._scan_callback)

    # If the rules file is modified, we are going to reload the rules.
    def on_modified(self, event):
        self.log.debug("Yara rule {0} modified".format(event.src_path))
        self._load_yara_rules()

    def _scan_callback(self, data):
        if data['matches']:
            # We want to make sure the offset is a str rather than int
            # so our output plays nicely. For instance, if we do not
            # do this, elasticsearch will assume that all objects in the
            # set are ints rather than a mix of int and str.
            strings = []
            for key in data['strings']:
                hit = (str(key[0]), key[1], key[2])
                strings.append(hit)
            data['strings'] = strings
            self.results.append(data)
        yara.CALLBACK_CONTINUE

    def _load_yara_rules(self):
        try:
            self.log.debug("Loading yara rules.")
            # We don't want to name our rules globally just yet, in case
            # loading fails.
            self.rule_lock.acquire()
            compiled_rules = yara.compile(self.yararules)
            self.rules = compiled_rules
            self.rule_lock.release()
        except Exception:
            self.log.critical("Error in yara rules. Compile failed.", exc_info=True)
            # If this is the first time we are loading the rules,
            # we are going to exit here.
            if not hasattr(self, 'rules'):
                exit(-1)

    def heartbeat(self):
        # Get the full absolute path of the yara rules directory
        yara_rules_base = os.path.dirname(os.path.abspath(self.yararules))

        # Instantiate our observer.
        observer = Observer()
        observer.schedule(self, yara_rules_base, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
