#!/bin/env python
#-*- coding:utf-8 -*-
__author__ = 'iambocai'
import ConfigParser
import json
import time
import socket
import os
import re
import sys
import commands
import urllib2, base64

class RedisStats:
    # 如果你是自己编译部署到redis，请将下面的值替换为你到redis-cli路径
    _redis_cli = '/usr/bin/redis-cli'
    _stat_regex = re.compile(ur'(\w+):([0-9]+\.?[0-9]*)\r')

    def __init__(self,  port='6379', passwd=None, host='127.0.0.1'):
        self._cmd = '%s -h %s -p %s info' % (self._redis_cli, host, port)
        if passwd not in ['', None]:
            self._cmd = '%s -h %s -p %s -a %s info' % (self._redis_cli, host, port, passwd)

    def stats(self):
        ' Return a dict containing redis stats '
        info = commands.getoutput(self._cmd)
        return dict(self._stat_regex.findall(info))


def main():
    cp = ConfigParser.RawConfigParser()
    cp.read('redis.properties')
    endpoint = cp.get("redis", "endpoint")
    step = cp.getint("redis", "step")
    conf_list = cp.get("redis","conf_list")
    push = cp.get("redis","push")
    debug = cp.getboolean("redis","debug")

    timestamp = int(time.time())
    # inst_list中保存了redis配置文件列表，程序将从这些配置中读取port和password，建议使用动态发现的方法获得，如：
    # inst_list = [ i for i in commands.getoutput("find  /etc/ -name 'redis*.conf'" ).split('\n') ]
    insts_list = conf_list.split(",")
    p = []
    
    monit_keys = [
        ('connected_clients','GAUGE'), 
        ('blocked_clients','GAUGE'), 
        ('used_memory','GAUGE'),
        ('used_memory_rss','GAUGE'),
        ('mem_fragmentation_ratio','GAUGE'),
        ('total_commands_processed','COUNTER'),
        ('rejected_connections','COUNTER'),
        ('expired_keys','COUNTER'),
        ('evicted_keys','COUNTER'),
        ('keyspace_hits','COUNTER'),
        ('keyspace_misses','COUNTER'),
        ('keyspace_hit_ratio','GAUGE'),
    ]
  
    for inst in insts_list:
        port = commands.getoutput("sed -n 's/^port *\([0-9]\{4,5\}\)/\\1/p' %s" % inst)
        passwd = commands.getoutput("sed -n 's/^requirepass *\([^ ]*\)/\\1/p' %s" % inst)
        metric = "redis"
        tags = 'port=%s' % port

        try:
            conn = RedisStats(port, passwd)
            stats = conn.stats()
        except Exception,e:
            continue

        for key,vtype in monit_keys:
            #一些老版本的redis中info输出的信息很少，如果缺少一些我们需要采集的key就跳过
            if key not in stats.keys():
                continue
            #计算命中率
            if key == 'keyspace_hit_ratio':
                try:
                    value = float(stats['keyspace_hits'])/(int(stats['keyspace_hits']) + int(stats['keyspace_misses']))
                except ZeroDivisionError:
                    value = 0
            #碎片率是浮点数
            elif key == 'mem_fragmentation_ratio':
                value = float(stats[key])
            else:
                #其他的都采集成counter，int
                try:
                    value = int(stats[key])
                except:
                    continue

            i = {
                'Metric': '%s.%s' % (metric, key),
                'Endpoint': endpoint,
                'Timestamp': timestamp,
                'Step': step,
                'Value': value,
                'CounterType': vtype,
                'TAGS': tags
            }
            p.append(i)
        
    if debug :
        print json.dumps(p, sort_keys=True,indent=4)

    method = "POST"
    handler = urllib2.HTTPHandler()
    opener = urllib2.build_opener(handler)
    url = push
    request = urllib2.Request(url, data=json.dumps(p) )
    request.add_header("Content-Type",'application/json')
    request.get_method = lambda: method
    try:
        connection = opener.open(request)
    except urllib2.HTTPError,e:
        connection = e

    # check. Substitute with appropriate HTTP code.
    if connection.code == 200:
        if debug:
            print connection.read()
    else:
        print '{"err":1,"msg":"%s"}' % connection
if __name__ == '__main__':
    proc = commands.getoutput(' ps -ef|grep %s|grep -v grep|wc -l ' % os.path.basename(sys.argv[0]))
    sys.stdout.flush()
    if int(proc) < 5:
        main()
