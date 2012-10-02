#  Copyright 2008-2011 Nokia Siemens Networks Oyj
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
from math import ceil
import os
import random
import shutil
import time
import sys
import sqlite3
from sqlite3 import OperationalError
import copy


ROOT = os.path.dirname(__file__)
lib = os.path.join(ROOT, '..', 'lib')
src = os.path.join(ROOT, '..', 'src')

sys.path.insert(0, lib)
sys.path.insert(0, src)

from model import RIDE
from test_runner import Runner

start_time = None
end_time = None

db_connection = None
db_cursor = None

template_initfile =\
"""
*** Settings ***
<LIBRARY_ENTRY>

*** Variables ***
<VARIABLE_ENTRY>
"""

template_testsuite =\
"""
*Setting*	*Value*	*Value*	*Value*
<LIBRARY_ENTRY>

*Variable*	*Value*	*Value*	*Value*
<VARIABLE_ENTRY>

*Test Case*	*Action*	*Argument*	*Argument*
<TC_NAME>
<TC_KEYWORDS>

*Keyword*	*Action*	*Argument*	*Argument*
<TC_KEYWORD_ENTRY>
"""
verbs = ['do','make','execute','select','count','process','insert','validate','verify']
words = None

def do_test(seed, path):
    global start_time, end_time

    i = None
    try:
        ride_runner = init_ride_runner(seed, path)
        ride_runner.open_test_dir()
        end_time = time.time()
        print "ELAPSED: ", (end_time-start_time)
        return 'PASS', seed, i, path
    except Exception, err:
        print err
        print 'i = ', i
        print 'seed was', str(seed)
        print 'path was', path
        return 'FAIL', seed, i or 0, path


def _create_test_libraries(path, filecount = 10):
    global db_cursor, verbs, words

    libs = []

    for x in range(filecount):
        lib_main = random.choice(words).strip().capitalize()
        lib_name = "CustomLib%s" % lib_main
        libs.append(lib_name)
        db_cursor.execute("INSERT INTO source (path,type) VALUES ('%s','CUSTOMLIBRARY')" % lib_name)
        libfile = open("%s/%s.py" % (path,lib_name),"w")
        libfile.write(\
"""
import os,time

class %s:
    def __init__(self):
""" % lib_name)

        directory_looper = """\tfor dirname, dirnames, filenames in os.walk('.'):
            for subdirname in dirnames:
                print os.path.join(dirname, subdirname)
            for filename in filenames:
                print os.path.join(dirname, filename)"""
        sleeper = "\ttime.sleep(2)"

        libfile.write(random.choice([directory_looper, sleeper]) + "\n")

        for x in range(random.randint(2,5)):
            temp_verb = copy.copy(verbs)
            verb = random.choice(temp_verb).capitalize()
            temp_verb.remove(verb.lower())
            kw_name = verb + "_" + lib_main
            db_cursor.execute("INSERT INTO keywords (name,source) VALUES ('%s','%s')" % (kw_name,lib_name))
            print "KW %s IN %s" % (kw_name, lib_name)
            libfile.write(\
"""
    def %s():
        pass
""" % kw_name)

        libfile.write(\
"""
myinstance = %s()
""" % lib_name)
        libfile.close()

    initfile_lines = open("%s/__init__.txt" % path).readlines()
    index = 0
    for line in initfile_lines:
        if "*** Settings ***" in line:
            index += 1
            for lib_name in libs:
                initfile_lines.insert(index, "Library\t%s.py\n" % (os.getcwd() + "/" + path + "/" + lib_name))
                index += 1
            break
        index += 1

    fo = open("%s/__init__.txt" % path, "w")
    for line in initfile_lines:
        fo.write(line)
    fo.close()


def _create_test_suite(path, testcount = 20, filecount = 1):
    global db_cursor, verbs, words

    for testfile_index in range(filecount):
        libraries_in_use = {}
        settings_txt = ""
        test_txt = ""
        keywords_txt = ""
        available_libraries = db_cursor.execute("SELECT path FROM source WHERE type = 'CUSTOMLIBRARY'").fetchall()
        tcfile = open("%s/CustomTests_%d.txt" % (path, testfile_index+1),"w")
        test_txt += "*** Test Cases ***\n"
        for tc in range(testcount):
            selected_library = random.choice(available_libraries)[0]
            if selected_library not in libraries_in_use.values():
                libraries_in_use["Cus%d" % tc] = selected_library
            tc_name = "Test %s in %s #%d" % (random.choice(verbs), selected_library.split("CustomLib")[1], tc)
            print tc_name
            available_keywords = db_cursor.execute("SELECT * FROM keywords WHERE source = '%s' ORDER BY RANDOM()" % selected_library).fetchall()
            kw1 = available_keywords.pop()
            kw2 = available_keywords.pop()
            test_txt += "%s\t[Documentation]\t%s\n\t\t%s\n\t\t%s\n\n" % (tc_name, "Test %d" % tc, kw1[2] + "." +kw1[1].replace("_"," "), kw2[2] + "." +kw2[1].replace("_"," "))

        settings_txt += "*** Settings ***\n"
        for tc_withname,tc_name in libraries_in_use.iteritems():
            settings_txt += "Library    %45s.py\tWITH NAME\t%s\n" % (tc_name, tc_withname)
            #settings_txt += "Library    %45s\n" % (os.getcwd()+"/"+path+"/" +tc_name)
        settings_txt += "\n"
        keywords_txt += "*** Keywords ***\n"
        keywords_txt += "My Keyword\n\tNo Operation\n"
        tcfile.write(settings_txt)
        tcfile.write(test_txt)
        tcfile.write(keywords_txt)
        tcfile.close()

def _create_test_project(path, testlibs_count = 5, testsuite_count = 5, tests_in_suite = 10):
    global template_initfile,template_testsuite

    _create_test_libraries(path, filecount=testlibs_count)
    _create_test_suite(path, testcount=tests_in_suite,filecount=testsuite_count)

def init_ride_runner(seed, path):
    global start_time
    shutil.rmtree(path, ignore_errors=True)
    #thedir = os.path.join("./", path)
    thetestdir = os.path.join(path, 'testdir')
    #os.makedirs(thetestdir)
    #os.makedirs(thetestdir + "/resources")
    shutil.copytree(os.path.join(ROOT, 'testdir'), thetestdir)
    _create_test_project(thetestdir)
    random.seed(seed)
    start_time = time.time()
    ride = RIDE(random, path)
    #ride_runner = Runner(ride, random)
    #if random.random() > 0.5:
    #    ride.open_test_dir()
    #else:
    #    ride.open_suite_file()
    return ride


def split(start, end):
    return int(ceil(float(end - start) / 2)) + start


def skip_steps(runner, number_of_steps):
    for i in range(number_of_steps):
        runner.skip_step()

def debug(seed, path, last_index, trace, start, end):
    if last_index == start:
        return trace + [last_index]
    if end <= start:
        return debug(seed, path, last_index, trace + [end], end+1, last_index)
    runner = init_ride_runner(seed, path)
    if trace != []:
        run_trace(runner, trace)
    midpoint = split(start, end)
    runner.skip_steps(midpoint)
    try:
        for j in range(midpoint, last_index):
            runner.step()
        return debug(seed, path, last_index, trace, start, midpoint-1)
    except Exception, err:
        if runner.count == last_index:
            return debug(seed, path, last_index, trace, midpoint, end)
        else:
            print 'New exception during debugging!'
            return debug(seed, path, runner.count, trace, midpoint, runner.count)

def run_trace(runner, trace):
    i = 0
    while i < trace[-1]:
        if i in trace:
            runner.step()
        else:
            runner.skip_step()
        i += 1

def generate_seed():
    seed = long(time.time() * 256)
    return seed

def _debugging(seed, path, i):
    print '='*80
    trace = debug(seed, path, i, [], 0, i)
    print '#'*80
    print trace
    print '%'*80
    print 'seed = ', seed
    run_trace(init_ride_runner(seed, path), trace)

def main(path):
    global db_connection, db_cursor, words

    words = open("testwords.txt").readlines()

    db_connection=sqlite3.connect("testdata.db")
    db_cursor=db_connection.cursor()
    try:
        db_cursor.execute('CREATE TABLE IF NOT EXISTS source (id INTEGER PRIMARY KEY, path TEXT, type TEXT)')
        db_cursor.execute('CREATE TABLE IF NOT EXISTS keywords (id INTEGER PRIMARY KEY, name TEXT, source TEXT, arguments INTEGER, returns INTEGER)')
        db_cursor.execute('DELETE FROM source')
        db_cursor.execute('INSERT INTO source (path,type) VALUES ("BuiltIn","LIBRARY")')
        db_cursor.execute('INSERT INTO source (path,type) VALUES ("OperatingSystem","LIBRARY")')
        db_cursor.execute('INSERT INTO source (path,type) VALUES ("String","LIBRARY")')
        db_cursor.execute('INSERT INTO keywords (name,source,arguments,returns) VALUES ("Log","BuiltIn",1,0)')
        db_cursor.execute('INSERT INTO keywords (name,source,arguments,returns) VALUES ("No Operation","BuiltIn",0,0)')
        db_cursor.execute('INSERT INTO keywords (name,source,arguments,returns) VALUES ("Get Time","BuiltIn",0,1)')
        db_cursor.execute('INSERT INTO keywords (name,source,arguments,returns) VALUES ("Count Files In Directory","Operating System",0,1)')
        db_cursor.execute('INSERT INTO keywords (name,source,arguments,returns) VALUES ("Get Environment Variables","BuiltIn",0,1)')
        db_cursor.execute('INSERT INTO keywords (name,source,arguments,returns) VALUES ("Get Time","BuiltIn",0,1)')
    except OperationalError, err:
        print "DB error: ",err
    db_connection.commit()

    result, seed, i, path = do_test(generate_seed(), path)
    #_debugging..
    return result != 'FAIL'

if __name__ == '__main__':
    if not main(sys.argv[1]):
        print 'error occurred!'
        sys.exit(1) #indicate failure
