# 
#           MuPIF: Multi-Physics Integration Framework 
#               Copyright (C) 2010-2014 Borek Patzak
# 
#    Czech Technical University, Faculty of Civil Engineering,
#  Department of Structural Mechanics, 166 29 Prague, Czech Republic
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, 
# Boston, MA  02110-1301  USA
#
import logging
logging.basicConfig(filename='mupif.log',filemode='w',level=logging.DEBUG)
logger = logging.getLogger('mupif')
import Pyro4
import socket
import subprocess
import time

Pyro4.config.SERIALIZER="pickle"
Pyro4.config.PICKLE_PROTOCOL_VERSION=2 #to work with python 2.x and 3.x
Pyro4.config.SERIALIZERS_ACCEPTED={'pickle'}

#First, check that we can connect to a listening port of a name server
#Second, connect there

def connectNameServer(nshost, nsport, hkey, timeOut=3.0):
    """
    Connects to a NameServer.
    
    :param str nshost: IP address of nameServer
    :param int nsport: Nameserver port.
    :param str hkey: A password string
    :param float timeOut: Waiting time for response in seconds
    :return: NameServer
    :rtype: Pyro4.naming.Nameserver
    :except: Can not connect to a LISTENING port of nameserver
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeOut)
        s.connect((nshost, nsport))
        s.close()
        logger.debug("Can connect to a LISTENING port of nameserver on " + nshost + ":" + str(nsport))
    except Exception as e:
        msg = "Can not connect to a LISTENING port of nameserver on " + nshost + ":" + str(nsport) + ". Does a firewall block INPUT or OUTPUT on the port? Exiting."
        logger.debug(msg)
        logger.exception(e)
        exit(1)

    #locate nameserver
    try:
        ns = Pyro4.locateNS(host=nshost, port=nsport,hmac_key=hkey)
        msg = "Connected to NameServer on %s:%s. Pyro4 version on your local computer is %s" %(nshost, nsport, Pyro4.constants.VERSION)
        logger.debug(msg)
    except Exception as e:
        msg = "Can not connect to NameServer on %s:%s. Is the NameServer running? Runs the NameServer on the same Pyro version as this version %s? Do you have the correct hmac_key (password is now %s)? Exiting." %(nshost, nsport, Pyro4.constants.VERSION, hkey)
        logger.debug(msg)
        logger.exception(e)
        exit(1)
    return ns


def connectApp(ns, name):
    """
    Connects to a remote application.
    
    :param Pyro4.naming.Nameserver ns: Instance of a nameServer
    :param str name: Name of the application to be connected to
    :return: Application
    :rtype: Instance of an application
    :except: Cannot find registered server or Cannot connect to application
    """
    try:
        uri = ns.lookup(name)
        logger.debug("Found URI %s from a nameServer %s" % (uri, ns) )
    except Exception as e:
        logger.error("Cannot find registered server %s on %s" % (name, ns) )
        return None
    app2 = Pyro4.Proxy(uri)
    try:
        sig = app2.getApplicationSignature()
        logger.debug("Connected to %s" % sig )
    except Exception as e:
        logger.debug("Cannot connect to application " + name + ". Is the server running?")
        logger.exception(e)
        return None
        #exit(e)
    return app2


def getNSAppName(jobname, appname):
    """
    Get application name.
    
    :param str jobname: Arbitrary string concatenated in the outut
    :param str appname: Arbitrary string concatenated in the outut
    :return: String of concatenated arguments
    :rtype: str
    """
    return 'Mupif'+'.'+jobname+'.'+appname

def runAppServer(server, port, nathost, natport, nshost, nsport, nsname, hkey, app):
    """
    Runs a simple application server

    :param str server: Host name of the server
    :param int port: Port number on the server where daemon will listen
    :param str nathost: Hostname of the server as reported by nameserver, for secure ssh tunnel it should be set to 'localhost' 
    :param int natport: Server NAT port as reported by nameserver
    :param str nshost: Hostname of the computer running nameserver
    :param int nsport: Nameserver port
    :param str nsname: Nameserver name to register application
    :param str hkey: A password string
    :param instance app: Application instance
    
    :except: Can not run Pyro4 daemon
    """
    try:
        daemon = Pyro4.Daemon(host=server, port=port, nathost=nathost, natport=natport)
        logger.info('Pyro4 daemon runs on %s:%d using nathost %s:%d and hmac %s' % (server, port, nathost, natport, hkey))
    except Exception as e:
        logger.debug('Can not run Pyro4 daemon on %s:%d using nathost %s:%d  and hmac %s' % (server, port, nathost, natport, hkey))
        logger.exception(e)
        exit(1)
    ns = connectNameServer(nshost, nsport, hkey)
    app.registerPyro(daemon, ns)
    #register agent
    uri = daemon.register(app)
    ns.register(nsname, uri)
    logger.debug('NameServer %s registered uri %s' % (nsname, uri) )
    daemon.requestLoop()
    logger.debug('Running runAppServer: server:%s, port:%d, nathost:%s, natport:%d, nameServer:%s, nameServerPort:%d, nameServerName:%s, URI %s' % (server, port, nathost, natport, nshost, nsport,nsname,uri) )


def sshTunnel(remoteHost, userName, localPort, remotePort, sshClient='ssh', options='', sshHost=''):
    """
    Automatic creation of ssh tunnel, using putty.exe for Windows and ssh for Linux
    
    :param str remoteHost: IP of remote host
    :param str userName: User name
    :param int localPort: Local port
    :param int remotePort: Remote port
    :param str sshClient: Path to executable ssh client (on Windows use double backslashes 'C:\\Program Files\\Putty\putty.exe')
    :param str options: Arguments to ssh clinent, e.g. the location of private ssh keyboard
    :param str sshHost: Computer used for tunelling
    
    :return: Instance of subprocess.Popen running the tunneling command
    :rtype: subprocess.Popen
    """
    
    if sshHost =='':
        sshHost = remoteHost
    #use direct system command. Paramiko or sshtunnel do not work.
    #put ssh public key on a server - interaction with a keyboard for password will not work here (password goes through TTY, not stdin)
    if sshClient=='ssh':
        cmd = 'ssh -L %d:%s:%d %s@%s -N %s' % (localPort, remoteHost, remotePort, userName, sshHost, options)
        logger.debug("Creating ssh tunnel via command: " + cmd)
    elif sshClient=='autossh':
        cmd = 'autossh -L %d:%s:%d %s@%s -N %s' % (localPort, remoteHost, remotePort, userName, sshHost, options)
        logger.debug("Creating autossh tunnel via command: " + cmd)
    elif 'putty' in sshClient.lower():
        #need to create a public key *.ppk using puttygen. It can be created by importing Linux private key. The path to that key is given as -i option
        cmd = '%s -L %d:%s:%d %s@%s -N %s' % (sshClient, localPort, remoteHost, remotePort, userName, sshHost, options)
        logger.debug("Creating ssh tunnel via command: " + cmd)
    elif sshClient=='manual':
        #You need ssh server running, e.g. UNIX-sshd or WIN-freesshd
        cmd1 = 'ssh -L %d:%s:%d %s@%s' % (localPort, remoteHost, remotePort, userName, sshHost)
        cmd2 = 'putty.exe -L %d:%s:%d %s@%s %s' % (localPort, remoteHost, remotePort, userName, sshHost, options)
        logger.info("If ssh tunnel does not exist, do it manually using a command e.g. " + cmd1 + " , or " + cmd2)
        return None
    else:
        logger.error("Unknown ssh client, exiting")
        exit(0)
    try:
        tunnel = subprocess.Popen(cmd.split())
    except Exception as e:
        logger.debug("Creation of a tunnel failed. Can not execute the command: %s " % cmd)
        logger.exception(e)
        tunnel = None
    time.sleep(1.0)

    return tunnel 
