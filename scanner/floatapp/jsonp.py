import json
from functools import wraps
from flask import redirect, request, current_app
import re

jsonp_validator = re.compile("^[a-zA-Z0-9_\-.]{1,128}$")

def jsonp(f):
	"""Wraps JSONified output for JSONP"""
	@wraps(f)
	def decorated_function(*args, **kwargs):
		callback = request.args.get('callback', False)
		if callback and jsonp_validator.match(callback):
			content = str(callback) + '(' + str(f(*args,**kwargs).data) + ')'
			return current_app.response_class(content, mimetype='application/javascript')
		else:
			return f(*args, **kwargs)
	return decorated_function
