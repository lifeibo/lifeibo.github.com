#!/usr/bin/python

import os;

github_username=""
github_password=""

def expect_github(gitcmd, gitusername, password):
    cmd = 'expect -c " set timeout -1; spawn -noecho ' + gitcmd + '; expect *https://github.com*; send ' + gitusername + '\\r; expect *assword*; send ' + password + '\\r; interact;"'
    os.system(cmd)

os.system("rake generate")
expect_github("git push origin source:source", github_username, github_password)
expect_github("rake deploy", github_username, github_password)
