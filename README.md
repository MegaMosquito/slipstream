# slipstream

A simple python example that uses NVIDIA Deepstream 5.

I have written a blog article about this example as well:
    https://darlingevil.com/riding-nvidia's-slipstream,-with-python/

This container sets up an RTSP streaming pipeline, from your favorite RTSP input stream, through an NVIDIA Deepstream 5 pipeline, using the new Python bindings, and out to a local RTSP streaming server.

This example requires NVIDIA hardware. The container is *big* and takes quite a while to build on small machines like the nano. Currently this example works only on:
 - amd64 hardware with a recent NVIDIA GPU. I tested it on an NVIDIA T4, and
 - NVIDIA Jetson (arm64) hardware. I tested it on an NVIDIA nano.

The original example code is structured like this:
```
   create and configure element 0
   create and configure element 1
   ...
   create and configure element N
   
   add element 0 to pipeline
   add element 1 to pipeline
   ...
   add element N to pipeline

   link element 0 to element 1
   link element 1 to element 2
   ...
   link element N-1 to element N
```

I restructured it to have a more consolidated element-focused format for each element, like this:
```
   create and configure element X
   add element X to pipeline
   link element X-1 to element X
```

In my opinion, the structure I am using here is easier to understand, easier to use, much easier to update (e.g., to add or remove pipeline elements), and to re-use elements in different contexts.


### Usage:

1. prepare the host:
   - install docker
   - install current software for your NVIDIA GPU (e.g., CUDA and on Jetsons, JetPack)
   - configure the nvidia container runtime to be the default Docker runtime
   - install git, make, curl and jq (useful tools for development)
   - git clone this repo
   - cd into this repo's directory

2. Install the open-horizon Agent, and configure it for your Management Hub

3. Put your RTSP input URI into your shell environment, e.g.:

```
export RTSPINPUT='rtsp://x.x.x.x:8554/abc'
```

4. Setup your machiine for development

```
docker login ...
export DOCKERHUBID=...
```

5. Download the Deepstream Python bindings (I cannot include them here since a developer account login is required for download). Use the URL below; create a free NVIDIA developer account if you don't already have one; then login and download the python bindings into this directory. Here's the URL:

https://developer.nvidia.com/deepstream_python_v0.5

6. Build the container

```
make build
```

7. Run the container using the RTSP input stream you setup in step 3

```
make dev
# ... watch the output as it runs
# ... wait for the "Deepstream RTSP pipeline example is starting" message, then
# ... connect to the RTSP output stream to verify it works
Ctrl-C  # To stop it when you are finished
```

### Advanced:

Once you have verified things with the above, take a look at the source code:
```
deepstream-rtsp.py
deepstream-rtsp.cfg
```
The python code is heavily commented (almost half of it is comment lines):
```
 $ wc -l deepstream-rtsp.py
742 deepstream-rtsp.py
 $ grep -c '\S*#' deepstream-rtsp.py
297
 $ 
 ```
There's also a lot of white space to separate the pipeline elements for easier reading (IMO, of course).

The `.cfg` file contains the configuration for `nvinfer` which does the inferencing (e.g., model, weights, labels).

If you wish, you can make changes to replace the inferencing engine with one of your own, or to change the input source type (e.g., a file instead of an RTSP stream) or to change the output (e.g., direct it to a screen window instead of the RTSP stream output used here).
