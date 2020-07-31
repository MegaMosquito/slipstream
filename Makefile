# A simple python example using NVIDIA's Deepstream 5

# An example public RTSP stream you can use for development:
#  export RTSPINPUT=rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov

NAME:="slipstream"
VERSION:="1.1.0"

# Get the hardware architecture type, and default LAN IP address for this host
# If my "helper" program doesn't work for you here, just set them manually!
ARCH:=$(shell ./helper -a)
IPADDR:=$(shell ./helper -i)

# Different base images for different hardware architectures:
BASE_IMAGE.aarch64:=nvcr.io/nvidia/deepstream-l4t:5.0-dp-20.04-samples
BASE_IMAGE.amd64:=nvcr.io/nvidia/deepstream:5.0-dp-20.04-triton
BASE_IMAGE.x86_64:=nvcr.io/nvidia/deepstream:5.0-dp-20.04-triton

run: validate-rtspinput clean
	@echo "\n\n"
	@echo "***   Using RTSP input URI: $(RTSPINPUT)"
	@echo "***   Output stream URI is: rtsp://$(IPADDR):8554/ds"
	@echo "\n\n"
	docker run -d \
	  --name ${NAME} \
	  --shm-size=1g --ulimit memlock=-1 --ulimit stack=67108864 \
	  -e RTSPINPUT="${RTSPINPUT}" \
	  -e ARCH=$(ARCH) \
	  -e IPADDR=$(IPADDR) \
	  -p 8554:8554 \
	  $(DOCKERHUB_ID)/$(NAME)_$(ARCH):$(VERSION)

dev: validate-rtspinput clean
	docker run -it -v `pwd`:/outside \
	  --name ${NAME} \
	  --shm-size=1g --ulimit memlock=-1 --ulimit stack=67108864 \
	  -e RTSPINPUT="${RTSPINPUT}" \
	  -e ARCH=$(ARCH) \
	  -e IPADDR=$(IPADDR) \
	  -e SHOW_FRAMES=no \
	  -p 8554:8554 \
	  $(DOCKERHUB_ID)/$(NAME)_$(ARCH):$(VERSION) /bin/bash

build: validate-dockerhubid validate-python-binding
	docker build --build-arg BASE_IMAGE=$(BASE_IMAGE.$(ARCH)) -t $(DOCKERHUB_ID)/$(NAME)_$(ARCH):$(VERSION) .

push: validate-dockerhubid
	docker push $(DOCKERHUB_ID)/$(NAME)_$(ARCH):$(VERSION) 

clean: validate-dockerhubid
	@docker rm -f ${NAME} >/dev/null 2>&1 || :


#
# Sanity check targets
#


validate-python-binding:
	@if [ "" = "$(wildcard deepstream_python_v*.tbz2)" ]; \
	  then { echo "***** ERROR: First download the Deepstream Python bindings into this directory!"; echo "*****        USE this URL:  https://developer.nvidia.com/python-sample-apps-bindings-v09"; exit 1; }; \
        fi
	@sleep 1

validate-rtspinput:
	@if [ -z "${RTSPINPUT}" ]; \
          then { echo "***** ERROR: \"RTSPINPUT\" is not set!"; exit 1; }; \
          else echo "  NOTE: Using RTSP input stream: \"${RTSPINPUT}\""; \
        fi
	@sleep 1

validate-dockerhubid:
	@if [ -z "${DOCKERHUB_ID}" ]; \
          then { echo "***** ERROR: \"DOCKERHUB_ID\" is not set!"; exit 1; }; \
          else echo "  NOTE: Using DockerHubID: \"${DOCKERHUB_ID}\""; \
        fi
	@sleep 1


.PHONY: build run dev push clean validate-dockerhubid validate-rtspinput validate-python-binding
