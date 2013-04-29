from flask import Response
import subprocess
import os
import sys

class ProcessWrapper(object):
	def __init__(self, process, done):
		self.process = process
		self.done = done
	def close(self):
		self.done()
		if self.process.returncode is not None:
			return
		self.process.stdout.close()
		self.process.terminate()
		self.process.wait()
	def __iter__(self):
		return self
	def __del__(self):
		self.close()
	def next(self):
		try:
			data = self.process.stdout.readline()
		except:
			self.close()
			raise StopIteration()
		if data:
			return data
		self.close()
		raise StopIteration()

def send_process(args, pid_file):
	def setup_proc():
		f = open(pid_file, "w")
		f.write(str(os.getpid()))
		f.close()
		os.close(0)
		os.dup2(1, 2)
	def tear_down_proc():
		try:
			os.unlink(pid_file)
		except:
			pass
	if os.path.exists(pid_file):
		f = open(pid_file, "r")
		pid = f.read()
		f.close()
		if os.path.exists("/proc/%s/status" % pid):
			return Response("Scanner is already running.\n", mimetype="text/plain")
	process = subprocess.Popen(args, close_fds=True, stdout=subprocess.PIPE, preexec_fn=setup_proc)
	response = ProcessWrapper(process, tear_down_proc)
	return Response(response, direct_passthrough=True, mimetype="text/plain")
