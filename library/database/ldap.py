#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2014, Jakub Jirutka <jakub@jirutka.cz>
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
module: ldap
author: Jakub Jirutka
version_added: "never"
short_description: Manage entries in LDAP server.
description:
  - This module adds, modifies and removes entries in LDAP server, similarly as
    C(ldapmodify) command.
options:
  bin_dn:
    description:
      - Distinguished name (DN) to bind (authenticate) to the LDAP server. It's usually DN of
        the LDAP superuser.
    required: true
  bind_password:
    description:
      - Password for a simple authentication.
    required: true
  content:
    description:
      - When used instead of C(src), sets the LDIF directly to the specified value.
    required: false
  ldap_uri:
    description:
      - URI of the LDAP server to connect to.
    required: false
    default: ldap://localhost:389
  remove_unset_attrs:
    description:
      - When an existing entry contains attributes that are not specified in the updated entry and
        this is set to C(yes), then these attributes will be removed.
    required: false
    default: no
    choices: [yes, no]
  src:
    description:
      - Path of a LDIF file on the local server; can be absolute or relative. If the path ends with
        C(.j2), then it is considered as a Jinja2 formatted template.
      - When C(state=absent), then the file may contain just distinguished names (DN) separated by
        a new line.
    required: false
  state:
    description:
      - Whether the entries should exist, i.e. adds new and updates existing. When C(absent),
        removes the entries.
    required: false
    default: present
    choices: [present, absent]
  timeout:
    description:
      - A limit on the number of seconds that the action will wait for a response from
        the LDAP server.
    required: false
    default: 10
'''

EXAMPLES = '''
# Ensure entries in LDAP from LDIF file
- ldap: >
  ldap_uri=ldaps://grid.encom.com
  bind_dn='cn=master,dc=encom,dc=com'
  bind_password=top-secret
  src=base.ldif

# Ensure entry in LDAP from LDIF content
- ldap: >
  bind_dn='cn=master,dc=encom,dc=com'
  bind_password=top-secret
  content='dc: encom
    objectClass: top
    objectClass: domain'

# Remove entries from LDAP
- ldap: >
  bind_dn='cn=master,dc=encom,dc=com'
  bind_password=top-secret
  state=absent
  content='cn=clue,ou=People,dc=encom,dc=com
           cn=jarvis,ou=People,dc=encom,dc=com'
'''

from StringIO import StringIO

try:
    import ldap
    from ldap.modlist import addModlist, modifyModlist
    from ldif import LDIFRecordList
    HAS_PYTHON_LDAP = True
except ImportError:
    HAS_PYTHON_LDAP = False


class LDAPModule(object):

    def __init__(self, params, dryrun=False):
        '''
        :param params: hash of parameters
        :param dryrun: if True then no write operation will be made in LDAP
        '''
        self.remove_unset_attrs = params['remove_unset_attrs']
        self.dryrun = dryrun

        self._conn = ldap.initialize(params['ldap_uri'])
        self._conn.protocol_version = ldap.VERSION3
        self._conn.timeout = int(params['timeout'])
        self._conn.network_timeout = int(params['timeout'])
        self._conn.simple_bind_s(params['bind_dn'], params['bind_password'])

    def close(self):
        '''Closes the LDAP connection.
        '''
        self._conn.unbind_s()

    def delete(self, dn):
        try:
            if not self.dryrun:
                self._conn.delete_s(dn)
            changed = True
        except ldap.NO_SUCH_OBJECT:
            changed = False

        return changed

    def delete_all(self, dn_list):
        '''Deletes all entries with the given DN, ignores missing.

        :param dn_list: list of DNs to delete
        :returns: True if any entry was actually deleted, False otherwise
        '''
        changed = False
        for dn in dn_list:
            if self.delete(dn): changed = True

        return changed

    def insert(self, dn, attrs):
        modlist = addModlist(attrs)
        if not self.dryrun:
            self._conn.add_s(dn, modlist)

        return True

    def update(self, dn, old_attrs, new_attrs):
        modlist = modifyModlist(old_attrs, new_attrs,
                                ignore_oldexistent=not(self.remove_unset_attrs))
        if modlist and not self.dryrun:
            self._conn.modify_s(dn, modlist)

        return bool(modlist)

    def upsert(self, dn, attrs):
        try:
            old_entry = self._conn.search_s(dn, ldap.SCOPE_BASE)
            changed = self.update(dn, old_entry[0][1], attrs)
        except ldap.NO_SUCH_OBJECT:
            changed = self.insert(dn, attrs)

        return changed

    def upsert_all(self, records):
        '''Updates existing entries or inserts new ones when doesn't exist yet.

        :param records: list of entries to update or insert; each item must be
            a tuple with DN and a hash of attributes
        :returns: True if any entry was changed, False otherwise
        '''
        changed = False
        for (dn, attrs) in records:
            if self.upsert(dn, attrs): changed = True

        return changed


def parse_ldif(ldif):
    '''
    :param ldif: string in LDIF format to parse
    :returns: list of tuples where the first item of the tuple is DN and the
        second one is a hash of attributes
    '''
    parser = LDIFRecordList(StringIO(ldif))
    parser.parse()

    return parser.all_records


def main():
    # define module
    module = AnsibleModule(
        argument_spec={
            'bind_dn':            {'required': True},
            'bind_password':      {'required': True},
            'content':            {'required': True, 'no_log': True},
            'ldap_uri':           {'aliases': ['ldap_url'], 'default': 'ldap://localhost:389'},
            'remove_unset_attrs': {'default': False, 'type': 'bool'},
            'state':              {'default': 'present', 'choices': ['present', 'absent']},
            'timeout':            {'default': 10, 'type': 'int'},
            'src':                {},  # used in ldap plugin runner to load content from file
        },
        supports_check_mode=True,
    )
    content = module.params['content']

    if not HAS_PYTHON_LDAP:
        module.fail_json(msg='Could not import python module: ldap. Please install python-ldap.')

    ldapm = None
    changed = False
    try:
        ldapm = LDAPModule(module.params, module.check_mode)
        ldif = parse_ldif(content)

        if module.params['state'] == 'absent':
            dn_list = [dn for dn, attrs in ldif] or content.splitlines()
            dn_list = [dn for dn in dn_list if dn.strip()]  # remove blanks
            changed = ldapm.delete_all(dn_list)
        else:
            changed = ldapm.upsert_all(ldif)

    except ldap.LDAPError, e:
        module.fail_json(msg=e.message)
    else:
        module.exit_json(changed=changed)
    finally:
        if ldapm: ldapm.close()


# import module snippets
from ansible.module_utils.basic import *
main()
