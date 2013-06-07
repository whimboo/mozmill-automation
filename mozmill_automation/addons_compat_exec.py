import optparse

from compat_by_default import CompatibleByDefault


def compat_addons_cli():
    usage = "usage: %prog [options] config-file"
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--repository',
                      dest='repository',
                      help='URL of a remote or local mozmill-test repository.')
    (options, args) = parser.parse_args()

    if not len(args) is 1:
        parser.error('A configuration file has to be specified.')

    cbd = CompatibleByDefault(args[0], options.repository)
    cbd.run()
