#!/usr/bin/env python3
"""
Zabbix Script for HP MSA Devices - Ultimate Version (Performance Enabled)
========================================================================
Versão Integrada com Correção para Enclosures, Fans e Power Supplies.

Monitoramento HPE MSA via API.
Base de Desenvolvimento: Template HPE MSA for Zabbix 4.4 with SSL
Versão: 1.0.1 (2026-06-24)
Desenvolvido por: Daniel Barcelini (Apoio: Gemini)

"""

import os
import json
import shutil
import urllib3
from hashlib import md5
from socket import gethostbyname
from argparse import ArgumentParser
from xml.etree import ElementTree as eTree
from datetime import datetime, timedelta, timezone
import sqlite3
import requests
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MSA_PARTS = (
    'disks', 'vdisks', 'controllers', 'enclosures', 'fans', 'power-supplies', 
    'ports', 'pools', 'disk-groups', 'volumes',
    'host-port-statistics', 'controller-statistics', 'volume-statistics', 'vdisk-statistics'
)

def install_script(tmp_dir, group):
    try:
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)
            os.chmod(tmp_dir, 0o775)
            print("Cache directory was created at: '{}'".format(tmp_dir))
    except PermissionError:
        raise SystemExit("ERROR: You don't have permissions to create '{}' directory".format(tmp_dir))

    if not os.path.exists(CACHE_DB):
        sql_cmd('CREATE TABLE IF NOT EXISTS skey_cache ('
                'dns_name TEXT NOT NULL, '
                'ip TEXT NOT NULL, '
                'proto TEXT NOT NULL, '
                'expired TEXT NOT NULL, '
                'skey TEXT NOT NULL DEFAULT 0, '
                'PRIMARY KEY (dns_name, ip, proto))')
        os.chmod(CACHE_DB, 0o664)
        print("Cache database initialized as: '{}'".format(CACHE_DB))

    try:
        shutil.chown(tmp_dir, group=group)
        shutil.chown(CACHE_DB, group=group)
    except Exception:
        pass

def sql_cmd(cmd, params=None, fetch=False):
    conn = sqlite3.connect(CACHE_DB)
    cursor = conn.cursor()
    if params:
        cursor.execute(cmd, params)
    else:
        cursor.execute(cmd)
    if fetch:
        data = cursor.fetchall()
        conn.close()
        return data
    else:
        conn.commit()
        conn.close()

def make_cred_hash(string, isfile=False):
    if isfile:
        try:
            with open(string, 'r') as f:
                string = f.read().strip()
        except FileNotFoundError:
            raise SystemExit("ERROR: Login file '{}' not found".format(string))
    return md5(string.encode('utf-8')).hexdigest()

def get_skey(msa, cred_hash):
    proto = 'https' if USE_SSL else 'http'
    cached = sql_cmd("SELECT skey, expired FROM skey_cache WHERE dns_name = ? AND ip = ? AND proto = ?", (msa[1], msa[0], proto), fetch=True)
    if cached:
        skey, expired_str = cached[0]
        expired = datetime.strptime(expired_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < expired:
            return skey

    url = "{}://{}/api/login/{}".format(proto, msa[0], cred_hash)
    try:
        res = requests.get(url, verify=VERIFY_SSL if USE_SSL else False, timeout=TIMEOUT)
        if res.status_code == 200:
            tree = eTree.fromstring(res.text)
            skey_elem = tree.find(".//PROPERTY[@name='response-numeric']")
            if skey_elem is None or not skey_elem.text:
                skey_elem = tree.find(".//PROPERTY[@name='response']")
                
            if skey_elem is not None and skey_elem.text:
                skey = skey_elem.text
                expired = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
                sql_cmd("INSERT OR REPLACE INTO skey_cache (dns_name, ip, proto, expired, skey) VALUES (?, ?, ?, ?, ?)", (msa[1], msa[0], proto, expired, skey))
                return skey
    except Exception:
        pass
    return None

def get_xml_data(msa, command, skey):
    proto = 'https' if USE_SSL else 'http'
    url = "{}://{}/api/show/{}".format(proto, msa[0], command)
    headers = {"sessionKey": skey} if skey else {}
    try:
        res = requests.get(url, headers=headers, verify=VERIFY_SSL if USE_SSL else False, timeout=TIMEOUT)
        if res.status_code == 200:
            return eTree.fromstring(res.text)
    except Exception:
        return None
    return None

def make_lld(msa, part, skey):
    tree = get_xml_data(msa, part, skey)
    lld_data = []
    if tree is not None:
        if part == 'controllers':
            for obj in tree.findall(".//OBJECT[@name='controllers']"):
                lld_data.append({"{#CONTROLLER.ID}": obj.find("./PROPERTY[@name='controller-id']").text})
        elif part == 'controller-statistics':
            for obj in tree.findall(".//OBJECT[@name='controller-statistics']"):
                lld_data.append({"{#CONTROLLER.ID}": obj.find("./PROPERTY[@name='durable-id']").text.replace('controller_', '')})
        elif part == 'ports':
            for obj in tree.findall(".//OBJECT[@name='ports']"):
                lld_data.append({"{#PORT.ID}": obj.find("./PROPERTY[@name='port']").text})
        elif part == 'host-port-statistics':
            for obj in tree.findall(".//OBJECT[@name='host-port-statistics']"):
                pid_elem = obj.find("./PROPERTY[@name='durable-id']")
                if pid_elem is not None:
                    lld_data.append({"{#PORT.ID}": pid_elem.text.replace('hostport_', '')})
        elif part == 'disks':
            for obj in tree.findall(".//OBJECT[@name='drive']"):
                lld_data.append({"{#DISK.ID}": obj.find("./PROPERTY[@name='location']").text})
        elif part == 'volumes':
            for obj in tree.findall(".//OBJECT[@name='volume']"):
                lld_data.append({"{#VOLUME.NAME}": obj.find("./PROPERTY[@name='volume-name']").text})
        elif part == 'volume-statistics':
            for obj in tree.findall(".//OBJECT[@name='volume-statistics']"):
                vname_elem = obj.find("./PROPERTY[@name='name']")
                if vname_elem is None:
                    vname_elem = obj.find("./PROPERTY[@name='volume-name']")
                if vname_elem is not None:
                    lld_data.append({"{#VOLUME.NAME}": vname_elem.text})
        elif part == 'vdisks':
            for obj in tree.findall(".//OBJECT[@name='virtual-disk']"):
                lld_data.append({"{#VDISK.ID}": obj.find("./PROPERTY[@name='name']").text})
        elif part == 'vdisk-statistics':
            for obj in tree.findall(".//OBJECT[@name='vdisk-statistics']"):
                vdid_elem = obj.find("./PROPERTY[@name='name']")
                if vdid_elem is None:
                    vdid_elem = obj.find("./PROPERTY[@name='vdisk-name']")
                if vdid_elem is not None:
                    lld_data.append({"{#VDISK.ID}": vdid_elem.text})
        elif part == 'enclosures':
            for obj in tree.findall(".//OBJECT") if tree.find(".//OBJECT[@name='enclosure']") is None else tree.findall(".//OBJECT[@name='enclosure']"):
                eid_elem = obj.find("./PROPERTY[@name='enclosure-id']")
                if eid_elem is not None:
                    lld_data.append({"{#ENCLOSURE.ID}": eid_elem.text})
        elif part == 'fans':
            for obj in tree.findall(".//OBJECT"):
                fid_elem = obj.find("./PROPERTY[@name='name']") or obj.find("./PROPERTY[@name='location']")
                if fid_elem is not None and ('fan' in fid_elem.text.lower() or 'psu' in fid_elem.text.lower()):
                    lld_data.append({"{#FAN.ID}": fid_elem.text})
        elif part == 'power-supplies':
            for obj in tree.findall(".//OBJECT"):
                psu_elem = obj.find("./PROPERTY[@name='name']") or obj.find("./PROPERTY[@name='serial-number']")
                if psu_elem is not None and ('psu' in psu_elem.text.lower() or 'power' in psu_elem.text.lower() or psu_elem.attrib.get('name') == 'serial-number'):
                    # Filtro basico para evitar duplicar objetos que nao sao fontes
                    name_str = psu_elem.text
                    lld_data.append({"{#PSU.ID}": name_str})
    return json.dumps(lld_data)

def _get_prop(obj, names, default="0"):
    if not isinstance(names, (list, tuple)):
        names = [names]
    for name in names:
        elem = obj.find("./PROPERTY[@name='{}']".format(name))
        if elem is not None and elem.text is not None:
            return elem.text
    return default

def get_full_json(msa, part, skey):
    tree = get_xml_data(msa, part, skey)
    full_data = {}
    if tree is not None:
        if part == 'controllers':
            for obj in tree.findall(".//OBJECT[@name='controllers']"):
                cid = _get_prop(obj, 'controller-id', 'Unknown')
                full_data[cid] = {
                    "h": _get_prop(obj, 'health-numeric'),
                    "rs": _get_prop(obj, 'redundancy-status-numeric'),
                    "cpu": _get_prop(obj, 'cpu-load'),
                    "io": _get_prop(obj, 'iops'),
                    "fh": _get_prop(obj, 'flash-health-numeric')
                }
        elif part == 'controller-statistics':
            for obj in tree.findall(".//OBJECT[@name='controller-statistics']"):
                cid = _get_prop(obj, 'durable-id', '').replace('controller_', '')
                full_data[cid] = {
                    "cpu": _get_prop(obj, 'cpu-load'),
                    "bps": _get_prop(obj, ['bytes-per-second-numeric', 'bytes-per-second']),
                    "iops": _get_prop(obj, 'iops'),
                    "reads": _get_prop(obj, 'number-of-reads'),
                    "writes": _get_prop(obj, 'number-of-writes'),
                    "data_read": _get_prop(obj, ['data-read-numeric', 'data-read']),
                    "data_write": _get_prop(obj, ['data-written-numeric', 'data-written'])
                }
        elif part == 'ports':
            for obj in tree.findall(".//OBJECT[@name='ports']"):
                pid = _get_prop(obj, 'port', 'Unknown')
                full_data[pid] = {
                    "h": _get_prop(obj, 'health-numeric'),
                    "ps": _get_prop(obj, 'status-numeric')
                }
        elif part == 'host-port-statistics':
            for obj in tree.findall(".//OBJECT[@name='host-port-statistics']"):
                pid = _get_prop(obj, 'durable-id', '').replace('hostport_', '')
                if not pid: continue
                full_data[pid] = {
                    "bps": _get_prop(obj, ['bytes-per-second-numeric', 'bytes-per-second']),
                    "iops": _get_prop(obj, 'iops'),
                    "reads": _get_prop(obj, 'number-of-reads'),
                    "writes": _get_prop(obj, 'number-of-writes'),
                    "data_read": _get_prop(obj, ['data-read-numeric', 'data-read']),
                    "data_write": _get_prop(obj, ['data-written-numeric', 'data-written']),
                    "resp_time": _get_prop(obj, ['io-resp-time', 'avg-io-resp-time'])
                }
        elif part == 'disks':
            for obj in tree.findall(".//OBJECT[@name='drive']"):
                did = _get_prop(obj, 'location', 'Unknown')
                full_data[did] = {
                    "h": _get_prop(obj, 'health-numeric'),
                    "cj": _get_prop(obj, 'curr-job-numeric')
                }
        elif part == 'volumes':
            for obj in tree.findall(".//OBJECT[@name='volume']"):
                vname = _get_prop(obj, 'volume-name', 'Unknown')
                full_data[vname] = {
                    "f": _get_prop(obj, 'free-size-numeric')
                }
        elif part == 'volume-statistics':
            for obj in tree.findall(".//OBJECT[@name='volume-statistics']"):
                vname = _get_prop(obj, ['name', 'volume-name'], '')
                if not vname: continue
                full_data[vname] = {
                    "bps": _get_prop(obj, ['bytes-per-second-numeric', 'bytes-per-second']),
                    "iops": _get_prop(obj, 'iops'),
                    "reads": _get_prop(obj, 'number-of-reads'),
                    "writes": _get_prop(obj, 'number-of-writes'),
                    "data_read": _get_prop(obj, ['data-read-numeric', 'data-read']),
                    "data_write": _get_prop(obj, ['data-written-numeric', 'data-written'])
                }
        elif part == 'vdisks':
            for obj in tree.findall(".//OBJECT[@name='virtual-disk']"):
                vdid = _get_prop(obj, 'name', 'Unknown')
                full_data[vdid] = {
                    "h": _get_prop(obj, 'health-numeric')
                }
        elif part == 'vdisk-statistics':
            for obj in tree.findall(".//OBJECT[@name='vdisk-statistics']"):
                vdid = _get_prop(obj, ['name', 'vdisk-name'], '')
                if not vdid: continue
                full_data[vdid] = {
                    "bps": _get_prop(obj, ['bytes-per-second-numeric', 'bytes-per-second']),
                    "iops": _get_prop(obj, 'iops'),
                    "reads": _get_prop(obj, 'number-of-reads'),
                    "writes": _get_prop(obj, 'number-of-writes'),
                    "data_read": _get_prop(obj, ['data-read-numeric', 'data-read']),
                    "data_write": _get_prop(obj, ['data-written-numeric', 'data-written']),
                    "resp_time": _get_prop(obj, ['io-resp-time', 'avg-io-resp-time']),
                    "read_resp_time": _get_prop(obj, 'read-resp-time'),
                    "write_resp_time": _get_prop(obj, 'write-resp-time')
                }
        elif part == 'enclosures':
            for obj in tree.findall(".//OBJECT"):
                eid = _get_prop(obj, 'enclosure-id', None)
                if eid:
                    full_data[eid] = {
                        "h": _get_prop(obj, ['health-numeric', 'status-numeric'])
                    }
        elif part == 'fans':
            for obj in tree.findall(".//OBJECT"):
                fid = _get_prop(obj, 'name', None) or _get_prop(obj, 'location', None)
                if fid and ('fan' in fid.lower() or 'psu' in fid.lower()):
                    full_data[fid] = {
                        "status": _get_prop(obj, ['status-numeric', 'health-numeric', 'health'])
                    }
        elif part == 'power-supplies':
            for obj in tree.findall(".//OBJECT"):
                psuid = _get_prop(obj, 'name', None) or _get_prop(obj, 'serial-number', None)
                if psuid and ('psu' in psuid.lower() or 'power' in psuid.lower() or 'left' in psuid.lower() or 'right' in psuid.lower()):
                    full_data[psuid] = {
                        "status": _get_prop(obj, ['status-numeric', 'health-numeric', 'health'])
                    }
    return json.dumps(full_data)

if __name__ == '__main__':
    main_parser = ArgumentParser(description="Zabbix HP MSA Ultimate Performance Collector")
    main_parser.add_argument('--ssl', choices=('direct', 'none', 'verify'), default='direct')
    main_parser.add_argument('-a', '--api', default='2')
    main_parser.add_argument('-u', '--user', dest='username', default='monitor')
    main_parser.add_argument('-p', '--password', dest='password', default='!monitor')
    main_parser.add_argument('--login-file', nargs=1, default=None)
    main_parser.add_argument('--save-xml', action='store_true')
    main_parser.add_argument('--tmp-dir', default='/tmp/zbx-hpmsa/')
    main_parser.add_argument('--group', default=None)
    
    subparsers = main_parser.add_subparsers(dest='command', required=True)
    subparsers.add_parser('install')
    
    lld_parser = subparsers.add_parser('lld')
    lld_parser.add_argument('msa')
    lld_parser.add_argument('part', choices=MSA_PARTS)

    full_parser = subparsers.add_parser('full')
    full_parser.add_argument('msa')
    full_parser.add_argument('part', choices=MSA_PARTS)

    args = main_parser.parse_args()
    API_VERSION = args.api
    TMP_DIR = args.tmp_dir
    CACHE_DB = TMP_DIR.rstrip('/') + '/zbx-hpmsa.cache.db'
    TIMEOUT = 12

    if args.command in ('lld', 'full'):
        SAVE_XML = args.save_xml
        USE_SSL = args.ssl in ('direct', 'verify')
        VERIFY_SSL = args.ssl == 'verify'
        MSA_USERNAME = args.username
        MSA_PASSWORD = args.password
        
        if all(x.isdigit() for x in args.msa.split('.')):
            MSA_CONNECT = (args.msa, args.msa)
        else:
            MSA_CONNECT = (gethostbyname(args.msa), args.msa)

        CRED_HASH = make_cred_hash(args.login_file[0], isfile=True) if args.login_file else make_cred_hash('_'.join([MSA_USERNAME, MSA_PASSWORD]))
        skey = get_skey(MSA_CONNECT, CRED_HASH)

        if args.command == 'lld':
            print(make_lld(MSA_CONNECT, args.part, skey))
        elif args.command == 'full':
            print(get_full_json(MSA_CONNECT, args.part, skey))
            
    elif args.command == 'install':
        install_script(TMP_DIR, args.group)
