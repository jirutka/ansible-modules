#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2014-2015, Jakub Jirutka <jakub@jirutka.cz>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: mongodb_replset
author: Jakub Jirutka
version_added: "never"
short_description: Initiate or extend replica set.
description:
  - This module allows to initiate a new replica set or add new members to an
    existing one. It can't remove members from a replica set, this should be
    always done with caution by hand.
options:
  login_user:
    description:
      - The username used to authenticate with.
    aliases: [ user ]
  login_password:
    description:
      - The password used to authenticate with.
    aliases: [ password ]
  login_host:
    description:
      - The first host to connect when initiating the replica set.
    aliases: [ host ]
    default: localhost
  login_port:
    description:
      - Port of the first host to connect when initiating the replica set.
    aliases: [ port ]
    default: 27017
  hosts:
    description:
      - A comma delimited list of replica set members.
    required: true
    aliases: [ members ]
    example: mongo0,mango1:27011,mango2:27012
  replica_set:
    description:
      - Name of the replica set to create or connect to.
    required: true
    aliases: [ replset ]
    default: "rs0"
'''

import ConfigParser
try:
    from pymongo.errors import ConnectionFailure, OperationFailure, ConfigurationError
    from pymongo import MongoClient
    from pymongo.mongo_replica_set_client import MongoReplicaSetClient
    from pymongo.read_preferences import ReadPreference
    from pymongo.uri_parser import split_hosts
    pymongo_found = True
except ImportError:
    pymongo_found = False


def read_mongocnf_creds():
    """ Read credentials from ~/.mongodb.cnf file, when exists.

    :return: tuple of username and password
    """
    config = ConfigParser.RawConfigParser()
    try:
        config.read(os.path.expanduser('~/.mongodb.cnf'))
        return (config.get('client', 'user'), config.get('client', 'pass'))
    except (ConfigParser.Error, IOError):
        return (None, None)


def replset_conf(client):
    """ Return replica set configuration; the same as rs.conf() in shell.

    :param client: initialized Mongo client
    :return: replica set config
    """
    return client['local'].system.replset.find_one()


def add_members(client, members):
    """ Add new members to the replica set.

    :param client: initialized Mongo client
    :param members: list of tuples that defines hostnames and ports of the
                    replica set members;
                    example: `[(mango0, 27017), (mango1, 27018)]`
    """
    conf = replset_conf(client)
    curr_hosts = [m['host'] for m in conf['members']]
    new_hosts = format_hosts(members)

    new_id = max([int(x['_id']) for x in conf['members']]) + 1
    for host in (set(new_hosts) - set(curr_hosts)):
        conf['members'] += [{'_id': new_id, 'host': host}]
        new_id += 1

    conf['version'] += 1
    client.admin.command('replSetReconfig', conf)


def members_state(client):
    """ Return dict of the replica set members with their state info. """
    members = client.admin.command('replSetGetStatus')['members']
    return dict((m['name'], {'state': m['stateStr']}) for m in members)


def replset_initiate(client, name, members):
    """ Initiate replica set with the specified members.

    :param client: initialized Mongo client
    :param name: name of the replica set to initiate
    :param members: list of tuples that defines hostnames and ports of the
                    replica set members;
                    example: `[(mango0, 27017), (mango1, 27018)]`
    """
    hosts = [{'_id': idx, 'host': join_colon(val)} for idx, val in enumerate(members)]
    conf = {'_id': name, 'members': hosts}
    client.admin.command('replSetInitiate', conf)


def format_hosts(members):
    """
    :param members: list of tuples that contain a hostname and a port
    :return: list of strings of the form `hostname[:port]`
    """
    return [join_colon(x) for x in members]


def join_colon(iterable):
    return ':'.join(str(s) for s in iterable)


def main():
    module = AnsibleModule(
        argument_spec={
            'login_user':     {'aliases': ['user']},
            'login_password': {'aliases': ['password'], no_log: True},
            'login_host':     {'aliases': ['host'], 'default': 'localhost'},
            'login_port':     {'aliases': ['port'], 'default': 27017},
            'hosts':          {'aliases': ['members'], 'required': True},
            'replica_set':    {'aliases': ['replset'], 'required': True}
        },
        required_together=[['login_host', 'login_port']]
    )

    if not pymongo_found:
        module.fail_json(msg='Python module "pymongo" must be installed.')

    user, password, host, port, hosts, replset = (
        module.params[k] for k in ['login_user', 'login_password', 'login_host',
                                   'login_port', 'hosts', 'replica_set'])
    nodes = split_hosts(hosts)

    if not user and not password:
        user, password = read_mongocnf_creds()

    initiated = False
    try:
        try:
            client = MongoReplicaSetClient(hosts, replicaSet=replset,
                                           read_preference=ReadPreference.PRIMARY)
            initiated = True
        except ConfigurationError, e:
            if 'is not a member of replica set' in e.message:
                client = MongoClient(host, int(port), read_preference=ReadPreference.SECONDARY)
            else:
                module.fail_json(msg="Unable to connect: %s" % e)

        if user and password:
            try:
                client.admin.authenticate(user, password)
            except OperationFailure, e:
                pass  # try to continue, maybe admin account is not set yet

    except ConnectionFailure, e:
        module.fail_json(msg="unable to connect to database: %s" % e)

    if initiated:
        changed = True
        absent_hosts = client.hosts - set(nodes)
        new_hosts = set(nodes) - client.hosts

        if absent_hosts:
            module.fail_json(msg="This module doesn't support members removing",
                             absent_hosts=format_hosts(absent_hosts),
                             members=members_state(client))
        elif new_hosts:
            try:
                add_members(client, nodes)
            except OperationFailure, e:
                module.fail_json(msg="Unable to add new members: %s" % e,
                                 new_hosts=format_hosts(new_hosts),
                                 members=members_state(client))
        else:
            changed = False

        module.exit_json(changed=changed,
                         added_hosts=format_hosts(new_hosts),
                         members=members_state(client))
    else:
        try:
            replset_initiate(client, replset, nodes)
            module.exit_json(changed=True, members=members_state(client))
        except OperationFailure, e:
            module.fail_json(msg="Unable to initiate replica set: %s" % e)

# import module snippets
from ansible.module_utils.basic import *
main()
