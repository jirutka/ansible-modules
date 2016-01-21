#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2015, Jakub Jirutka <jakub@jirutka.cz>
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
module: nameservers_facts
author: Jakub Jirutka
version_added: "never"
short_description: Collects nameservers from /etc/resolv.conf as facts.
description:
  - Exposes nameservers from C(/etc/resolv.conf) as facts under the key C(ansible_nameservers).
'''


def main():
    module = AnsibleModule({})

    nameservers = [
        re.split(r'\s+', line)[1]
        for line in open('/etc/resolv.conf')
        if line.lower().startswith('nameserver ')]

    module.exit_json(ansible_facts={'ansible_nameservers': nameservers})


# import module snippets
from ansible.module_utils.basic import *
main()
