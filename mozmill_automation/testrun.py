# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import optparse
import sys
import tempfile
import urllib

import manifestparser
import mozinstall
import mozmill
import mozmill.logger

import application
import errors
import files
import report
import reports
import repository


MOZMILL_TESTS_REPOSITORIES = {
    'firefox' : "http://hg.mozilla.org/qa/mozmill-tests",
    'thunderbird' : "http://hg.mozilla.org/users/bugzilla_standard8.plus.com/qa-tests/",
}


class TestRun(object):
    """ Class to execute a Mozmill test-run. """

    def __init__(self, args=sys.argv[1:], debug=False, repository_path=None,
                 manifest_path=None, timeout=None):

        usage = "usage: %prog [options] binary"
        parser = optparse.OptionParser(usage=usage)
        self.add_options(parser)
        self.options, self.args = parser.parse_args(args)

        if len(self.args) > 1:
            parser.error("Exactly one binary has to be specified.")

        self.binary = self.args[0]
        self.debug = debug
        self.timeout = timeout
        self.repository_path = repository_path
        self.manifest_path = manifest_path

        if self.options.repository_url:
            self.repository_url = self.options.repository_url
        else:
            self.repository_url = MOZMILL_TESTS_REPOSITORIES[self.options.application]

        self.addon_list = []
        self.downloaded_addons = []
        self.testrun_index = 0

        self.last_failed_tests = None
        self.last_exception = None

    def add_options(self, parser):
        """add options to the parser"""
        parser.add_option("-a", "--addons",
                          dest="addons",
                          action="append",
                          metavar="ADDONS",
                          help="add-ons to be installed")
        parser.add_option("--application",
                          dest="application",
                          default="firefox",
                          choices=["firefox", "thunderbird"],
                          metavar="APPLICATION",
                          help="application name [default: %default]")
        parser.add_option("--junit",
                          dest="junit_file",
                          metavar="PATH",
                          help="JUnit XML style report file")
        parser.add_option("--report",
                          dest="report_url",
                          metavar="URL",
                          help="send results to the report server")
        parser.add_option("--repository",
                          dest="repository_url",
                          metavar="URL",
                          help="URL of a custom repository")
        parser.add_option("--screenshot-path",
                          dest="screenshot_path",
                          metavar="PATH",
                          help="path to use for screenshots")
        parser.add_option("--tag",
                          dest="tags",
                          action="append",
                          metavar="TAG",
                          help="Tag to apply to the report")

        mozmill = optparse.OptionGroup(parser, "Mozmill options")
        mozmill.add_option("-l", "--logfile",
                          dest="logfile",
                          metavar="PATH",
                          help="path to log file")
        mozmill.add_option('-p', "--profile",
                          dest="profile",
                          metavar="PATH",
                          help="path to the profile")
        parser.add_option_group(mozmill)

    def _generate_custom_report(self):
        if self.options.junit_file:
            filename = files.get_unique_filename(self.options.junit_file,
                                                 self.testrun_index)
            custom_report = self.update_report(self._mozmill.mozmill.get_report())
            report.JUnitReport(custom_report, filename)

    def download_addon(self, url, target_path):
        """ Download the XPI file. """
        try:
            filename = url.split('?')[0].rstrip('/').rsplit('/', 1)[-1]
            target_path = os.path.join(target_path, filename)

            print "Downloading %s to %s" % (url, target_path)
            urllib.urlretrieve(url, target_path)

            return target_path
        except Exception, e:
            print e

    def prepare_addons(self):
        """ Prepare the addons for the test run. """

        for addon in self.options.addons:
            if addon.startswith("http") or addon.startswith("ftp"):
                path = self.download_addon(addon, tempfile.gettempdir())
                self.downloaded_addons.append(path)
                self.addon_list.append(path)
            else:
                self.addon_list.append(addon)

    def prepare_tests(self):
        """ Preparation which has to be done before starting a test. """

        # instantiate handlers
        logger = mozmill.logger.LoggerListener(log_file=self.options.logfile,
                                               console_level=self.debug and 'DEBUG' or 'INFO',
                                               file_level=self.debug and 'DEBUG' or 'INFO',
                                               debug=self.debug)
        handlers = [logger]
        if self.options.report_url:
            self.report = reports.DashboardReport(self.options.report_url, self)
            handlers.append(self.report)

        # instantiate MozMill
        profile_args = dict(addons=self.addon_list)
        runner_args = dict(binary=self._application)
        mozmill_args = dict(app=self.options.application,
                            handlers=handlers,
                            profile_args=profile_args,
                            runner_args=runner_args)
        if self.timeout:
            mozmill_args['jsbridge_timeout'] = self.timeout
        self._mozmill = mozmill.MozMill.create(**mozmill_args)

        self.graphics = None
        self._mozmill.add_listener(self.graphics_event, eventType='mozmill.graphics')

        if self.options.screenshot_path:
            path = os.path.abspath(self.options.screenshot_path)
            if not os.path.isdir(path):
                os.makedirs(path)
            self._mozmill.persisted["screenshotPath"] = path

    def graphics_event(self, obj):
        if not self.graphics:
            self.graphics = obj

    def remove_downloaded_addons(self):
        for path in self.downloaded_addons:
            try:
                # Remove downloaded add-on
                print "*** Removing downloaded add-on '%s'." % path
                os.remove(path)
            except:
                print "*** Failed to remove downloaded add-on '%s'." % path

    def run_tests(self):
        """ Start the execution of the tests. """

        self.prepare_tests()
        manifest = manifestparser.TestManifest(
            manifests=[os.path.join(self.repository_path, self.manifest_path)],
            strict=False)

        self._mozmill.run(manifest.tests)

        # Whenever a test fails it has to be marked, so we quit with the correct exit code
        self.last_failed_tests = self.last_failed_tests or self._mozmill.results.fails

        self._generate_custom_report()
        self.testrun_index += 1

    def run(self):
        """ Run tests for all specified builds. """

        try:
            # XXX: mktemp is marked as deprecated but lets use it because with
            # older versions of Mercurial the target folder should not exist.
            self.repository_path = tempfile.mktemp(".mozmill-tests")
            self._repository = repository.Repository(self.repository_url,
                                                     self.repository_path)
            self._repository.clone()
        except Exception, e:
            raise Exception("Failure in setting up the mozmill-tests repository. " +
                            e.message)

        if self.options.addons:
            self.prepare_addons()

        try:
            # Prepare the binary for the test run
            if mozinstall.is_installer(self.binary):
                install_path = tempfile.mkdtemp(".binary")
    
                print "Install build: %s" % self.binary
                self._folder = mozinstall.install(self.binary, install_path)
                self._application = mozinstall.get_binary(self._folder,
                                                          self.options.application)
            else:
                # TODO: Ensure that self._folder is the same as from mozinstall
                folder = os.path.dirname(self.binary)
                self._folder = folder if not os.path.isdir(self.binary) else self.binary
                self._application = self.binary

            # Prepare the repository
            ini = application.ApplicationIni(self._application)
            repository_url = ini.get('App', 'SourceRepository')
    
            # Update the mozmill-test repository to match the Gecko branch
            branch_name = self._repository.identify_branch(repository_url)
            self._repository.update(branch_name)

            self.run_tests()

        finally:
            self._mozmill.results.finish(self._mozmill.handlers)

            # Remove the build when it has been installed before
            if mozinstall.is_installer(self.binary):
                print "Uninstall build: %s" % self._folder
                mozinstall.uninstall(self._folder)

            self.remove_downloaded_addons()

            # Remove the temporarily cloned repository
            self._repository.remove()

            # If a test has been failed ensure that we exit with status 2
            if self.last_failed_tests:
                raise errors.TestFailedException()


class FunctionalTestRun(TestRun):
    """ Class to execute a Firefox functional test-run. """

    report_type = "firefox-functional"
    report_version = "2.0"

    def __init__(self, *args, **kwargs):
        TestRun.__init__(self, *args, **kwargs)

    def run_tests(self):
        """ Execute the functional tests. """

        try:
            self.manifest_path = os.path.join('tests',
                                              'functional',
                                              'testToolbar',
                                              'manifest.ini')
            TestRun.run_tests(self)
        except Exception, e:
            raise


def functional_cli():
    try:
        FunctionalTestRun().run()
    except errors.TestFailedException:
        sys.exit(2)
