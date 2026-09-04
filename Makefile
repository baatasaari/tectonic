.PHONY: pilot-up pilot-down pilot-health pilot-verify pilot-reset

pilot-up:
	./deploy/pilot/up.sh

pilot-down:
	./deploy/pilot/down.sh

pilot-health:
	python3 deploy/pilot/verify.py --phase full --health-only

pilot-verify:
	python3 deploy/pilot/verify.py --phase full

pilot-reset:
	./deploy/pilot/down.sh --volumes
	rm -rf deploy/pilot/state deploy/pilot/.env deploy/pilot/.env.runtime

