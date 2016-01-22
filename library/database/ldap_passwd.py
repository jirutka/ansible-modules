#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2016, Jakub Jirutka <jakub@jirutka.cz>
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

from __future__ import with_statement

DOCUMENTATION = '''
---
module: ldap_passwd
author: Jakub Jirutka
version_added: "never"
short_description: Change password of an LDAP or Active Directory user.
description:
  - This module modifies password of an LDAP or Active Directory user.
options:
  bind_dn:
    description:
      - Distinguished name (DN) to bind (authenticate) to the LDAP server. It's usually DN of
        the LDAP superuser.
    required: true
  bind_password:
    description:
      - Password for a simple authentication.
    required: true
  ldap_type:
    description:
      - Type of the LDAP server; C(ldap) for a standard LDAP, or C(ad) for an Active Directory.
    required: false
    default: ldap
    choices: [ldap, ad]
  ldap_uri:
    description:
      - URI of the LDAP server to connect to.
    required: false
    default: ldaps://localhost:636
  new_password:
    description:
      - The new password (in plain-text) to set for the user.
    required: true
  timeout:
    description:
      - A limit on the number of seconds that the action will wait for a response from
        the LDAP server.
    required: false
    default: 10
  user_dn:
    description:
      - Distinguished name (DN) of the user to change the password for.
    required: true
'''

EXAMPLES = '''
- ldap: >
  ldap_uri=ldaps://grid.encom.com
  bind_dn='cn=master,dc=encom,dc=com'
  bind_password=very-top-secret
  user_dn='uid=flynnkev,ou=people,dc=encom,dc=com'
  new_password=top-secret
'''

from contextlib import contextmanager
try:
    import ldap
    HAS_PYTHON_LDAP = True
except ImportError:
    HAS_PYTHON_LDAP = False


@contextmanager
def ldap_connection(uri, bind_dn=None, bind_password=None, timeout=10, opts={}):
    try:
        conn = ldap.initialize(uri)
        conn.protocol_version = ldap.VERSION3
        conn.timeout = int(timeout)
        conn.network_timeout = int(timeout)

        for k, v in opts.items():
            conn.set_option(k, v)

        if bind_dn and bind_password:
            conn.simple_bind_s(bind_dn, bind_password)

        yield conn
    finally:
        if conn: conn.unbind_s()


def change_password_ldap(conn, user_dn, new_password):
    conn.passwd_s(conn, None, new_password)


def change_password_ad(conn, user_dn, new_password):
    unicode_pwd = unicode('"%s"' % new_password).encode('utf-16-le')
    add_pass = [(ldap.MOD_REPLACE, 'unicodePwd', [unicode_pwd])]
    conn.modify_s(user_dn, add_pass)


def main():
    # define module
    module = AnsibleModule(
        argument_spec={
            'bind_dn':       {'required': True},
            'bind_password': {'required': True, 'no_log': True},
            'ldap_type':     {'default': 'ldap', 'choices': ['ldap', 'ad']},
            'ldap_uri':      {'aliases': ['ldap_url'], 'default': 'ldaps://localhost:636'},
            'new_password':  {'required': True, 'aliases': ['password'], 'not_log': True},
            'timeout':       {'default': 10, 'type': 'int'},
            'user_dn':       {'required': True}
        }
    )

    if not HAS_PYTHON_LDAP:
        module.fail_json(msg='Could not import python module: ldap. Please install python-ldap.')

    # Create type object as namespace for module params
    p = type('Params', (), module.params)

    if p.ldap_type == 'ad':
        change_password = change_password_ad
        opts = {ldap.OPT_X_TLS: ldap.OPT_X_TLS_DEMAND, ldap.OPT_X_TLS_DEMAND: True}
    else:
        change_password = change_password_ldap
        opts = {}

    try:
        with ldap_connection(p.ldap_uri, p.bind_dn, p.bind_password, p.timeout, opts) as c:
            change_password(c, p.user_dn, p.new_password)

    except ldap.LDAPError, e:
        module.fail_json(msg=e.message)
    else:
        module.exit_json(changed=True)


# import module snippets
from ansible.module_utils.basic import *
main()
