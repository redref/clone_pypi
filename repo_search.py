#!/bin/env python

"""
RPC INPUT Example:
 <?xml version='1.0'?>
 <methodCall>
 <methodName>search</methodName>
 <params>
 <param>
 <value><struct>
 <member>
 <name>name</name>
 <value><array><data>
 <value><string>toto</string></value>
 </data></array></value>
 </member>
 <member>
 <name>summary</name>
 <value><array><data>
 <value><string>toto</string></value>
 </data></array></value>
 </member>
 </struct></value>
 </param>
 <param>
 <value><string>or</string></value>
 </param>
 </params>
 </methodCall>

RPC OUTPUT Example:
<methodResponse>
<params>
<param>
<value><array><data>

    REPEAT :
        <value><struct>
        <member>
        <name>_pypi_ordering</name>
        <value><boolean>0</boolean></value>
        </member>
        <member>
        <name>version</name>
        <value><string>0.2</string></value>
        </member>
        <member>
        <name>name</name>
        <value><string>django-sparkle-1.5</string></value>
        </member>
        <member>
        <name>summary</name>
        <value><string>Django-sparkle is a Django application to make it easy to publish updates for your mac application using sparkle (intended for Django &gt;= 1.5)</string></value>
        </member>
        </struct></value>

FOOTER:
</data></array></value>
</param>
</params>
</methodResponse>

"""
import os
import re


def application(environ, start_response):
    status = '200 OK'
    output = "<methodResponse>\n<params>\n<param>\n<value><array><data>\n"

    search_term = False
    for line in environ['wsgi.input'].read().split('\n'):
        if line.startswith("<value><string>"):
            search_term = line.replace("<value><string>", '')
            search_term = search_term.replace("</string></value>", '')
            break

    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index'), 'r') as f:
        alls = f.readlines()
        p = re.compile(r'%s' % search_term)
        for line in alls:
            if p.match(line):
                res = line.split(' | ')
                res[2] = res[2].replace('<', '')
                res[2] = res[2].replace('>', '')
                res[2] = res[2].replace('&', '')
                res[2] = res[2].strip()
                output += "<value><struct>\n"
                output += "<member>\n<name>_pypi_ordering</name>\n<value><boolean>0</boolean></value>\n</member>\n"
                output += "<member>\n<name>version</name>\n<value><string>%s</string></value>\n</member>\n" % res[1]
                output += "<member>\n<name>name</name>\n<value><string>%s</string></value>\n</member>\n" % res[0]
                output += "<member>\n<name>summary</name>\n<value><string>%s</string></value>\n</member>\n" % res[2]
                output += "</struct></value>\n"

    output += "</data></array></value>\n</param>\n</params>\n</methodResponse>\n"

    response_headers = [
        ('Content-type', 'application/xml'),
        ('Content-Length', str(len(output)))]

    start_response(status, response_headers)
    return [output]

