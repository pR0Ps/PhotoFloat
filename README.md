# PhotoFloat
### A Web 2.0 Photo Gallery Done Right via Static JSON & Dynamic Javascript
#### by Jason A. Donenfeld (<Jason@zx2c4.com>)

![Screenshot](screenshot.jpg)

PhotoFloat is an open source web photo gallery aimed at sleekness and speed. It keeps with an old hat mentality, preferring to work over directory structures rather than esoteric photo database management software. Everything it generates is static, which means it's extremely fast.

[Check out a demo!](http://photos.jasondonenfeld.com/#santa_fe_and_telluride_8.19.10-8.27.10/western_202.jpg)

## How It Works

PhotoFloat consists of two segments – a Python script and a JavaScript application.

The Python script scans a directory tree of images, whereby each directory constitutes an album. It then populates a second folder, known as the cache folder with statically generated JSON files and thumbnails. The scanner extracts metadata from EXIF tags in JPEG photos. PhotoFloat is smart about file and directory modification time, so you are free to run the scanner script as many times as you want, and it will be very fast if there are few or zero changes since the last time you ran it.

The JavaScript application consists of a single `index.html` file with a single `scripts.min.js` and a single `styles.min.css`. It fetches the statically generated JSON files and thumbnails on the fly from the `cache` folder to create a speedy interface. Features include:

* Animations to make the interface feel nice
* Separate album view and photo view
* Album metadata pre-fetching
* Photo pre-loading
* Recursive async randomized tree walking album thumbnail algorithm
* Smooth up and down scaling
* Mouse-wheel support
* Metadata display
* Consistant hash url format
* Linkable states via ajax urls
* Static rendering for googlebot conforming to the AJAX crawling spec.
* Facebook meta tags for thumbnail and post type
* Link to original images (can be turned off)
* Optional Google Analytics integration
* Optional server-side authentication support
* A thousand other tweaks here and there...

It is, essentially, the slickest and fastest, most minimal but still well-featured photo gallery app on the net.

## Installation

#### Download the source code from the git repository:

    $ git clone git://git.zx2c4.com/PhotoFloat
    $ cd PhotoFloat

#### Change or delete the Google Analytics ID tracker:

To delete:

    $ rm web/js/999-googletracker.js

To change:

    $ vim web/js/999-googletracker.js

Modify the part that says UA-XXXXXX-X and put your own in there.

#### Tweak the index.html page to have a custom title or copyright notice.

    $ vim web/index.html

#### Build the web page.

This simply runs all the javascript through Google Closure Compiler and all the CSS through YUI Compressor to minify and concatenate everything. Be sure you have java installed.

    $ cd web
    $ make

#### Generate the albums:

Now that we're in the web directory, let's make a folder for cache and a folder for the pictures:

    $ mkdir albums
    $ mkdir cache

When you're done, fill albums with photos and directories of photos. You can also use symlinks. Run the static generator (you need Python≥2.6 and the Python Imaging Library):

    $ cd ../scanner
    $ ./main.py ../web/albums ../web/cache

After it finishes, you will be all set. Simply have your web server serve pages out of your web directory. You may want to do the scanning step in a cronjob, if you don't use the deployment makefiles mentioned below.

## Optional: Server-side Authentication

The JavaScript application uses a very simple API to determine if a photo can be viewed or not. If a JSON file returns error `403`, the album is hidden from view. To authenticate, `POST` a username and a password to `/auth`. If unsuccessful, `403` is returned. If successful, `200` is returned, and the previously denied json files may now be requested. If an unauthorized album is directly requested in a URL when the page loads, an authentication box is shown.

PhotoFloat ships with an optional server side component called FloatApp to faciliate this, which lives in `scanner/floatapp`. It is a simple Flask-based Python web application.

#### Edit the app.cfg configuration file:

    $ cd scanner/floatapp
    $ vim app.cfg

Give this file a correct username and password, for both an admin user and a photo user, as well as a secret token. The admin user is allowed to call `/scan`, which automatically runs the scanner script mentioned in the previous section.

#### Decide which albums or photos are protected:

    $ vim auth.txt

This file takes one path per line. It restricts access to all photos in this path. If the path is a single photo, then that single photo is restricted.

#### Configure nginx:

FloatApp makes use of `X-Accel-Buffering` and `X-Accel-Redirect` to force the server-side component to have minimal overhead. Here is an example nginx configuration that can be tweaked:

    server {                                                                                                               
            listen 80;                                                                                                     
            server_name photos.jasondonenfeld.com;                                                                         
            location / {
                    index index.html;
                    root /var/www/htdocs/photos.jasondonenfeld.com;
            }
    
            include uwsgi_params;
            location /albums/ {
                    uwsgi_pass unix:/var/run/uwsgi-apps/photofloat.socket;
            }
            location /cache/ {
                    uwsgi_pass unix:/var/run/uwsgi-apps/photofloat.socket;
            }
            location /scan {
                    uwsgi_pass unix:/var/run/uwsgi-apps/photofloat.socket;
            }
            location /auth {
                    uwsgi_pass unix:/var/run/uwsgi-apps/photofloat.socket;
            }
            location /photos {
                    uwsgi_pass unix:/var/run/uwsgi-apps/photofloat.socket;
            }
    
            location /internal-cache/ {
                    internal;
                    alias /var/www/uwsgi/photofloat/cache/;
            }
            location /internal-albums/ {
                    internal;
                    alias /var/www/uwsgi/photofloat/albums/;
            }
    }

Note that the `internal-*` paths must match that of `app.cfg`. This makes use of uwsgi for execution:

    metheny ~ # cat /etc/uwsgi.d/photofloat.ini 
    [uwsgi]
    chdir = /var/www/uwsgi/%n
    master = true
    uid = %n
    gid = %n
    chmod-socket = 660
    chown-socket = %n:nginx
    socket = /var/run/uwsgi-apps/%n.socket
    logto = /var/log/uwsgi/%n.log
    processes = 4
    idle = 1800
    die-on-idle = true
    plugins = python27
    module = floatapp:app

## Optional: Deployment Makefiles

Both the scanner and the webpage have a `make deploy` target, and the scanner has a `make scan` target, to automatically deploy assets to a remote server and run the scanner. For use, customize `deployment-config.mk` in the root of the project, and carefully read the `Makefile`s to learn what's happening.

## Mailing List & Suggestions

If you have any suggestions, feel free to contact the PhotoFloat community via [our mailing list](http://lists.zx2c4.com/mailman/listinfo/photofloat). We're open to adding all sorts of features and working on integration points with other pieces of software.

## License

Copyright (C) 2010 - 2014 Jason A. Donenfeld. All Rights Reserved.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
