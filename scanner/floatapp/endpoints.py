from floatapp import app
from floatapp.login import admin_required, login_required, is_authenticated, query_is_photo_user, query_is_admin_user, photo_user, admin_user
from floatapp.jsonp import jsonp
from process import send_process
from TreeWalker import TreeWalker
from flask import Response, abort, json, request, jsonify
from flask_login import login_user, current_user
from random import shuffle
import os
from mimetypes import guess_type

cwd = os.path.dirname(os.path.abspath(__file__))

@app.route("/scan")
@admin_required
def scan_photos():
	global cwd
	response = send_process([ "stdbuf", "-oL", os.path.abspath(os.path.join(cwd, "../main.py")),
				os.path.abspath(app.config["ALBUM_PATH"]), os.path.abspath(app.config["CACHE_PATH"]) ],
				os.path.join(cwd, "scanner.pid"))
	response.headers.add("X-Accel-Buffering", "no")
	response.cache_control.no_cache = True
	return response

@app.route("/auth")
def login():
	success = False
	if current_user.is_authenticated():
		success = True
	elif query_is_photo_user(request.form) or query_is_photo_user(request.args):
		success = login_user(photo_user, remember=True)
	elif query_is_admin_user(request.form) or query_is_admin_user(request.args):
		success = login_user(admin_user, remember=True)
	if not success:
		abort(403)
	return ""

def cache_base(path):
	path = path.replace('/', '-').replace(' ', '_').replace('(', '').replace('&', '').replace(',', '').replace(')', '').replace('#', '').replace('[', '').replace(']', '').replace('"', '').replace("'", '').replace('_-_', '-').lower()
	while path.find("--") != -1:
		path = path.replace("--", "-")
	while path.find("__") != -1:
		path = path.replace("__", "_")
	if len(path) == 0:
		path = "root"
	return path

auth_list = [ ]
def read_auth_list():
	global auth_list, cwd
	f = open(os.path.join(cwd, "auth.txt"), "r")
	paths = [ ]
	for path in f:
		path = path.strip()
		paths.append(path)
		paths.append(cache_base(path))
	f.close()
	auth_list = paths

# TODO: Make this run via inotify
read_auth_list()

def check_permissions(path):
	if not is_authenticated():
		for auth_path in auth_list:
			if path.startswith(auth_path):
				abort(403)

@app.route("/albums/<path:path>")
def albums(path):
	check_permissions(path)
	return accel_redirect(app.config["ALBUM_ACCEL"], app.config["ALBUM_PATH"], path)

@app.route("/cache/<path:path>")
def cache(path):
	check_permissions(path)
	return accel_redirect(app.config["CACHE_ACCEL"], app.config["CACHE_PATH"], path)

def accel_redirect(internal, real, relative_name):
	real_path = os.path.join(real, relative_name)
	internal_path = os.path.join(internal, relative_name)
	if not os.path.isfile(real_path):
		abort(404)
	mimetype = None
	types = guess_type(real_path)
	if len(types) != 0:
		mimetype = types[0]
	response = Response(mimetype=mimetype)
	response.headers.add("X-Accel-Redirect", internal_path)
	response.cache_control.public = True
	if mimetype == "application/json":
		response.cache_control.max_age = 3600
	else:
		response.cache_control.max_age = 29030400
	return response

@app.route("/photos")
@jsonp
def photos():
	f = open(os.path.join(app.config["CACHE_PATH"], "all_photos.json"), "r")
	photos = json.load(f)
	f.close()
	if not is_authenticated():
		def allowed(photo):
			for auth_path in auth_list:
				if photo.startswith(auth_path):
					return False
			return True
		photos = [photo for photo in photos if allowed(photo)]
	count = int(request.args.get("count", len(photos)))
	random = request.args.get("random") == "true"
	if random:
		shuffle(photos)
	else:
		photos.reverse()
	response = jsonify(photos=photos[0:count])
	response.cache_control.no_cache = True
	return response
