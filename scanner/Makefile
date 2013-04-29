.PHONY: deploy scan

include ../deployment-config.mk
include floatapp/app.cfg

SSH_OPTS := -q -o ControlMaster=auto -o ControlPath=.ssh-deployment.sock

scan:
	@echo "    SCAN    $(WEB_SERVER)"
	@curl "$(WEB_SERVER_URL)/scan?username=$(subst $\",,$(ADMIN_USERNAME))&password=$(subst $\",,$(ADMIN_USERNAME))"

deploy:
	@echo "    SSH     $(WEB_SERVER)"
	@ssh $(SSH_OPTS) -Nf $(WEB_SERVER)
	
	@echo "    RSYNC   . $(WEB_SERVER):$(FLASK_PATH)"
	@ssh -t $(SSH_OPTS) $(WEB_SERVER) "sudo -u $(FLASK_USER) -v"
	@rsync -aizm --delete-excluded --exclude=.ssh-deployment.sock --exclude=Makefile --exclude="*.pyc" \
		--filter="P floatapp/auth.txt" --filter="P albums/" --filter="P cache/" --exclude=.gitignore --exclude="*.swp" \
		--rsh="ssh $(SSH_OPTS)" --rsync-path="sudo -n -u $(FLASK_USER) rsync" \
		. "$(WEB_SERVER):$(FLASK_PATH)" 
	
	@echo "    CHMOD   750/640 $(WEB_SERVER):$(FLASK_PATH)/*"
	@ssh -t $(SSH_OPTS) $(WEB_SERVER) "sudo find -P '$(FLASK_PATH)' \! -path '$(FLASK_PATH)/albums/*' \! -path '$(FLASK_PATH)/cache/*' -type f -exec chmod 640 {} \;; \
					sudo find -P '$(FLASK_PATH)' \! -path '$(FLASK_PATH)/albums/*' \! -path '$(FLASK_PATH)/cache/*' -type d -exec chmod 750 {} \;; \
					sudo chmod 750 $(FLASK_PATH)/main.py"
	
	@echo "    CHOWN   $(FLASK_USER):$(HTDOCS_USER) $(WEB_SERVER):$(FLASK_PATH){,albums,cache}"
	@ssh -t $(SSH_OPTS) $(WEB_SERVER) "sudo chown $(FLASK_USER):$(HTDOCS_USER) '$(FLASK_PATH)' '$(FLASK_PATH)/albums' '$(FLASK_PATH)/cache'"
	@echo "    CHMOD   710 $(WEB_SERVER):$(FLASK_PATH)"
	@ssh -t $(SSH_OPTS) $(WEB_SERVER) "sudo chmod 710 '$(FLASK_PATH)'"
	
	@echo "    UWSGI   restart $(WEB_SERVER)"
	@ssh -t $(SSH_OPTS) $(WEB_SERVER) "sudo /etc/init.d/uwsgi restart"
	
	@echo "    SSH     $(WEB_SERVER)"
	@ssh -O exit $(SSH_OPTS) $(WEB_SERVER)
