# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import ConfigParser
import os
import re
import sys

import errors


# List of available update channels
UPDATE_CHANNELS = ["nightly",
                   "aurora", "auroratest",
                   "beta", "betatest",
                   "release", "releasetest",
                   "esr", "esrtest"]


class ApplicationIni(object):
    """ Class to retrieve entries from the application.ini file. """

    def __init__(self, binary):
        self.ini_file = os.path.join(os.path.dirname(binary),
                                     'application.ini')

        self.config = ConfigParser.RawConfigParser()
        self.config.read(self.ini_file)

    def get(self, section, option):
        """ Retrieve the value of an entry. """
        return self.config.get(section, option)


class UpdateChannel(object):
    """ Class to handle the update channel. """

    pref_regex = "(?<=pref\(\"app\.update\.channel\", \")([^\"]*)(?=\"\))"

    def __init__(self, binary, *args, **kwargs):
        self.folder = os.path.dirname(binary)

    @property
    def channel_prefs_path(self):
        """ Returns the channel prefs path. """
        for pref_folder in ('preferences', 'pref'):
            pref_path = os.path.join(self.folder,
                                     'defaults',
                                     pref_folder,
                                     'channel-prefs.js')
            if os.path.exists(pref_path):
                return pref_path
        raise errors.NotFoundException('Channel prefs not found.', pref_path)

    def is_valid_channel(self, channel):
        """ Checks if the update channel is valid. """
        try:
            UPDATE_CHANNELS.index(channel);
            return True
        except:
            return False

    def _get_channel(self):
        """ Returns the current update channel. """
        try:
            file = open(self.channel_prefs_path, "r")
        except IOError:
            raise
        else:
            content = file.read()
            file.close()

            result = re.search(self.pref_regex, content)
            return result.group(0)

    def _set_channel(self, value):
        """ Sets the update channel. """

        print "Setting update channel to '%s'..." % value

        if not self.is_valid_channel(value):
            raise Exception("%s is not a valid update channel" % value)

        try:
            file = open(self.channel_prefs_path, "r")
        except IOError:
            raise
        else:
            # Replace the current update channel with the specified one
            content = file.read()
            file.close()

            # Replace the current channel with the specified one
            result = re.sub(self.pref_regex, value, content)

            try:
                file = open(self.channel_prefs_path, "w")
            except IOError:
                raise
            else:
                file.write(result)
                file.close()

                # Check that the correct channel has been set
                if value != self.channel:
                    raise Exception("Update channel wasn't set correctly.")

    channel = property(_get_channel, _set_channel, None)
