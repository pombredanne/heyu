# Copyright 2014 Rackspace
# All Rights Reserved.
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

import ConfigParser
import os
import re
import socket
import ssl

import tendril


# Default port for the HeyU hub
HEYU_PORT = 4859

# Regular expression for parsing a hub specification
HUB_RE = re.compile(r'^(?P<hostname>[^:\s\[\]]+|\[[0-9a-fA-F:]+\])'
                    r'(?::(?P<port>\d+))?$')


class HubException(Exception):
    """
    Exception raised if there's an error parsing the hub
    specification.
    """

    pass


def parse_hub(hub):
    """
    Parse a hub specification.

    :param hub: The hub specification.  Can be either a bare
                "hostname" or a "hostname:port".  If the hostname is
                an IPv6 address, it should be enclosed in brackets,
                i.e. "[::1]:4859".

    :returns: A tuple of the hostname and integer port number.
    """

    # Interpret the hostname
    match = HUB_RE.match(hub)
    if not match:
        raise HubException("Could not understand hub address '%s'" % hub)

    # Extract the hostname
    hostname = match.group('hostname')
    if hostname[0] == '[':
        # Unwrap an IPv6 address
        hostname = hostname[1:-1]

    # Now extract the port
    port = match.group('port')
    if port is None:
        port = HEYU_PORT
    else:
        port = int(port)

    # We have hostname and port, now let's resolve it
    try:
        result = socket.getaddrinfo(hostname, port, 0, socket.SOCK_STREAM)
    except Exception as e:
        raise HubException("Could not resolve hub hostname '%s': %s" %
                           (hostname, e))

    return result[0][4]


# Regular expression for parsing a certificate configuration
# specification
CERTCONF_RE = re.compile(r'^(?P<conf_path>[^\[\]]+)'
                         r'(?:\[(?P<profile>\w+)\])?$')


class CertException(Exception):
    """
    Exception raised if there's an error parsing the certificate
    configuration specification.
    """

    pass


def cert_wrapper(cert_conf, profile, server_side=False, secure=True):
    """
    Compute and return a ``tendril.TendrilPartial`` object which will
    set up TLS on the HeyU port.

    :param cert_conf: The path to the certificate profile
                      configuration file.  If ``None``, "~/.heyu.cert"
                      is used.  The path is tilde-expanded.  Note that
                      the path may included an alternate profile name,
                      enclosed in braces ('[]') and appended to the
                      end of the path; this will override the value of
                      ``profile``.
    :param profile: The name of the default profile to use.
    :param server_side: If ``True``, TLS will be set up for the server
                        side of the connection, rather than the client
                        side.  Defaults to ``False``.
    :param secure: If ``True``, TLS will be set up, and an error
                   raised if the certificate configuration file cannot
                   be found.  If ``False``, TLS will not be set up.

    :returns: A wrapper callable, suitable for use with Tendril, that
              will set up TLS authentication and encryption for the
              HeyU connection.
    """

    # Set up no wrappers if we're set up insecure
    if not secure:
        return None

    # We need to find the certificate configuration file...
    if cert_conf is None:
        cert_conf = '~/.heyu.cert'
    else:
        # Parse the configuration specification
        match = CERTCONF_RE.match(cert_conf)
        if not match:
            raise CertException("Could not understand certificate "
                                "configuration path '%s'" % cert_conf)

        # Set the stripped path
        cert_conf = match.group('conf_path')

        # Was the profile overridden?
        override = match.group('profile')
        if override:
            profile = override

    # Look up and read the certificate configuration
    cert_path = os.path.expanduser(cert_conf)
    cp = ConfigParser.SafeConfigParser()
    if not cp.read(cert_path):
        raise CertException("Could not read certificate configuration "
                            "file '%s'" % cert_path)

    # Suck in the profile
    try:
        conf = dict(cp.items(profile))
    except ConfigParser.NoSectionError:
        raise CertException("No such profile [%s] in configuration file '%s'" %
                            (profile, cert_path))
    except Exception as exc:
        raise CertException("Could not load profile [%s] from '%s': %s" %
                            (profile, cert_path, exc))

    # All we need now is the three essential configuration settings
    missing = [key for key in ('cafile', 'certfile', 'keyfile')
               if key not in conf]
    if missing:
        raise CertException("Missing configuration for the following "
                            "values in the [%s] profile of '%s': %s" %
                            (profile, cert_path, ', '.join(sorted(missing))))

    return tendril.TendrilPartial(
        ssl.wrap_socket,
        keyfile=conf['keyfile'], certfile=conf['certfile'],
        ca_certs=conf['cafile'],
        server_side=server_side, cert_reqs=ssl.CERT_REQUIRED,
        ssl_version=ssl.PROTOCOL_TLSv1)
