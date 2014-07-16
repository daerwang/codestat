#coding=utf-8
#/************************************************************
#  Author:        ycat
#  Date:          2014/07/16
#  Desc:		  parse one svn diff information 
#  Usage:         
#  History:
#      <author>      <time>         <desc>
#       ycat         2014/07/16     create
#***********************************************************/
import sys,os,re
import difflib
import sqlite3
import pytest
import platform

class svn_diff :
	'parse one svn diff info'
	re_comment = re.compile("^\+?(\s*/\*.*)|^\+?(\s*//.*)|(.*\*/\s*)$") # /* */ //
	re_revision = re.compile("^(?:(?:\+\+\+ )|(?:--- )).*\(.* (\d+)\)$") 	#+++ bin/unittest5.xml	(revision 10775) 
	re_delfile = re.compile("^@@\s+-\d+,\d+\s+\+0,0\s+@@$"); #@@ -1,10 +0,0 @@ 
	re_addfile = re.compile("^@@\s+-0,0\s+\+\d+,\d+\s+@@$"); #@@ -0,0 +1,10 @@ 
	operator_type_str = {0:"modify",1:"add",2:"del"}
	re_empty = re.compile("^[+-]?\s*(\^M)?\s*$")
	RESULT_TYPE_FAILED = 0
	RESULT_TYPE_CONTINUE = 1
	RESULT_TYPE_SUCCESS = 2
	
	def __init__(self):
		self.state = 0 # 0 for index, 1 for ====, 2 for ---, 3 for +++, 4 for content 
		self.file_name = "" 
		self.file_path = ""
		self.add_lines = 0 
		self.del_lines = 0
		self.add_comment_lines = 0 
		self.revision = -1
		self.old_revision = -1
		self.add_list = []
		self.del_list = []
		self.operator_type = 0
		self.repo_id = -1
		self.project = None
		self.move_lines = 0 #lines are same in del lines and add lines 

	def __str__(self):
		ret = "%s %s (r%d -- r%d)\n".encode("utf-8")% (svn_diff.operator_type_str[self.operator_type],
			self.file_path + '/' + self.file_name,self.old_revision,self.revision)
		ret += "add(%d) "%self.add_lines
		ret += "move(%d) "%self.move_lines
		ret += "comment(%d) "%self.add_comment_lines
		ret += "del(%d) "%self.del_lines
		ret += "valid(%d) "%self.valid_lines
		return ret
	
	@property
	def full_name(self):
		return self.file_path + '/' + self.file_name
	
	@staticmethod
	def is_first_line(line):
		return line[:6] == "Index:"
	
	@staticmethod
	def _is_empty_line(line):
		return svn_diff.re_empty.match(line) != None
	
	@staticmethod
	def _is_comment_line(line):
		return svn_diff.re_comment.match(line) != None

	@staticmethod
	def _is_del_file(line):
		return svn_diff.re_delfile.match(line) != None
		
	@staticmethod
	def _is_add_file(line):
		return svn_diff.re_addfile.match(line) != None
		
	@staticmethod
	def _get_revision(line):
		m = svn_diff.re_revision.match(line)
		if m :
			return int(m.group(1))
		else:
			return -1
	
	@property
	def valid_lines(self):
		i = self.add_lines - self.add_comment_lines - self.move_lines
		if i < 0: return 0
		return i
			
	@property
	def type(self):
		s = self.file_path.lower()
		if s.find('test/mock') != -1: return "mock"
		if s.find('test\\mock') != -1: return "mock"
		if s.find('test/') != -1: return "test"
		if s.find('test\\') != -1: return "test"
		return "src"
		
	def save_db(self,db,repo_id):
		s = "INSERT INTO r_svn_diff (file_path,file_name,add_lines,del_lines,move_lines,add_comment_lines,revision,old_revision,repo_id,valid_lines,operate_type,enabled)VALUES(?,?,?,?,?,?,?,?,?,?,?,1)"
		t = (self.file_path,self.file_name,self.add_lines,
			self.del_lines,self.move_lines,self.add_comment_lines,
			self.revision,self.old_revision,repo_id,self.valid_lines,self.operator_type)
		try:
			db.execute(s,t)
		except Exception as e:
			print("Run SQL: " + s + " failed! Exception: " + e.message)
			raise
	
	def read(self, line):
		if self.state == 0 :
			if not self.is_first_line(line):
				return self.RESULT_TYPE_FAILED
			else :
				self.state = 1
				self.file_name = line[7:]
				self.file_path = os.path.dirname(self.file_name)
				self.file_name =  os.path.basename(self.file_name) 
				return self.RESULT_TYPE_CONTINUE
				
		elif self.state == 1 :
			if line.strip() != "===================================================================":
				return self.RESULT_TYPE_FAILED
			else:
				self.state = 2
				return self.RESULT_TYPE_CONTINUE
				
		elif self.state == 2 :
			if line.find("Cannot display:") == 0:
				#binary type file 
				return self.RESULT_TYPE_SUCCESS
			if line[0:3] == "---" : 
				self.state = 3
				self.old_revision = self._get_revision(line)
				return self.RESULT_TYPE_CONTINUE
			return self.RESULT_TYPE_FAILED
			
		elif self.state == 3:
			if line[0:3] == "+++" : 
				self.state = 4
				self.revision = self._get_revision(line)
				return self.RESULT_TYPE_CONTINUE
			return self.RESULT_TYPE_FAILED
		elif self.state == 4:
			if line[0:2] != "@@" : 
				return self.RESULT_TYPE_FAILED
			if svn_diff._is_del_file(line) : 
				self.operator_type = 2
			elif svn_diff._is_add_file(line) : 
				self.operator_type = 1
			else:
				self.operator_type = 0		
			self.state = 5
			return self.RESULT_TYPE_CONTINUE
		else:  
			if len(line) == 0:
				return self.RESULT_TYPE_CONTINUE
			if self._is_empty_line(line) :
				return self.RESULT_TYPE_CONTINUE
			if line[0] == '-': 
				self.del_list.append(line[1:].strip())
				self.del_lines += 1
			elif line[0] == '+': 				
				self.add_lines += 1
				self.add_list.append(line[1:].strip())
				if self._is_comment_line(line):
					self.add_comment_lines+=1			
			return self.RESULT_TYPE_CONTINUE;	
	
	def count_result(self):
		self.move_lines = len([item for item in self.add_list if item in self.del_list ]) #求交集 

##############################################################################################
#	Unit test 		
##############################################################################################
def test_add_del_file():
	assert svn_diff._is_del_file("@@ -1,10 +0,0 @@") 
	assert not svn_diff._is_del_file("@@ -0,0 +1,10 @@") 
	assert not svn_diff._is_del_file("@@ -1,10 +1,0 @@") 
	assert not svn_diff._is_del_file("@@ -1,10 +0,0 @") 
	
	assert svn_diff._is_add_file("@@ -0,0 +1,10 @@") 
	assert not svn_diff._is_add_file("@@ -1,10 +0,0 @@") 
	assert not svn_diff._is_add_file("@@ -1,0 +1,10 @@") 
	assert not svn_diff._is_add_file("@@ -0,0 +1,10 @") 

def test__is_empty_line():
	assert svn_diff._is_empty_line("+   ")
	assert svn_diff._is_empty_line("-   ")
	assert (svn_diff._is_empty_line("+"))
	assert svn_diff._is_empty_line("+^M")
	assert svn_diff._is_empty_line("-^M")
	assert svn_diff._is_empty_line("^M")
	assert not svn_diff._is_empty_line("+      // friend class MyTimerHandler;^M")
	assert not svn_diff._is_empty_line("-      // friend class MyTimerHandler;^M")
	assert not svn_diff._is_empty_line("   // friend class MyTimerHandler;^M")
		
def test_is_first_line():
	assert svn_diff.is_first_line("Index: GWDLL2/src/TcpRouter/RouterClient.cpp") 
	assert svn_diff.is_first_line("Index: bin/unittest5.xml") 
	assert not (svn_diff.is_first_line("+++ src/NetLib/UdpClient.cpp	(working copy)"))
		
def test_iscomment():
	assert(svn_diff._is_comment_line(" \t /*"))
	assert(svn_diff._is_comment_line(" \t */"))
	assert(svn_diff._is_comment_line(" \t //sfdsfdsfsf  fdfdf  "))
	assert not(svn_diff._is_comment_line(" \t afdfsda//sfdsfdsfsf  fdfdf  "))
	assert not(svn_diff._is_comment_line(" \t afdfsda /* sfdsfdsfsf */ fdfdf  "))
	assert(svn_diff._is_comment_line("+/*   ACE_Thread_Manager* threadManager; ^M"))
	assert(svn_diff._is_comment_line("+// friend class MyTimerHandler;^M"))
	assert(svn_diff._is_comment_line("+ACE_Thread_Manager* threadManager; ^M */"))
	
def test_get_revision():
	assert svn_diff._get_revision("+++ src/NetLib/UdpClient.cpp	(working copy)") == -1
	assert svn_diff._get_revision("--- src/NetLib/UdpClient.cpp	(working copy)") == -1
	assert svn_diff._get_revision("--- src/NetLib/UdpClient.cpp	(revision 10460)")==10460
	assert svn_diff._get_revision("+++ src/NetLib/UdpClient.cpp	(revision 10460)")==10460
	assert svn_diff._get_revision("++ src/NetLib/UdpClient.cpp	(revision 10460)")== -1
	assert svn_diff._get_revision("+++ GWDLL2/include/GWUtility/TimerID.h  (revision 10450)")==10450
	assert svn_diff._get_revision("--- GWDLL2/include/GWUtility/TimerID.h  (revision 104250)")==104250
	assert svn_diff._get_revision('+++ GWDLL2/src/TcpRouter/RouterClient.cpp      ')==-1
	assert svn_diff._get_revision("+++ project1/branches/branch_1/C.txt	(版本 373)")==373
	assert svn_diff._get_revision("--- project1/branches/branch_1/C.txt	(版本 372)")==372
 
def test_type():
	s = svn_diff()
	s.file_path = r"test/TestGWUtility"
	assert 'test' == s.type
	
	s.file_path = r"test/TestGWUtility"
	assert 'test' == s.type
	
	s.file_path = r"include/GWUtility"
	assert 'src' == s.type
	
	s.file_path = r"src/OamApi"
	assert 'src' == s.type
	
	s.file_path = r"HENBGW\test\MockMME"
	assert 'mock' == s.type
	
def run_cur_tests():	
	if __name__ == '__main__':	
		print("python " + platform.python_version())
		os.chdir(os.path.dirname(__file__))
		pytest.main("-v -x " + os.path.split(__file__)[1])	

run_cur_tests()
if __name__ == '__main__':
	os.remove("./test_db.db")


	
