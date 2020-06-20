#!/usr/bin/env python3

################################################################################
# Copyright (c) 2020, NVIDIA CORPORATION. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
################################################################################





#
# Some NVIDIA example code modified by MegaMosquito (mosquito@darlingevil.com)
#
# The NVIDIA Deepstream examples are awesome on their own but I wanted to
# create an end-to-end RTSP pipeline for inferencing. This example begins
# with an RTSP video input stream. That stream is piped through an example
# inferencing engine, and ultimately produces an annotated RTSP output stream.
# To accomplish this I combined a couple of the NVIDIA-provided examples...
#
#   Most of the code here was taken from:
#     /opt/nvidia/deepstream/deepstream-5.0/sources/python/apps/deepstream-test1-rtsp-out
#
#   The RTSP stream input element was taken from:
#    /opt/nvidia/deepstream/deepstream-5.0/sources/python/apps/deepstream-imagedata-multistream
#
# After you install the Deepstream 5 python bindings those files will be in
# the path locations shown above.
#
# I have tried to explain how things work below so you can take this as a
# starting point, then add, remove and/or replace selected pipeline elements
# to create your own Deepstream application.
#

# Debug print on/off (there are better ways to do this)
def debug(s):
  # print(s)
  pass





# When you edit the source you may need to also edit this CONFIG_FILE (here
# in the same directory with this source file). It contains configuration
# arguments for the inferencing "element" in the pipeline, and anything else
# you wish, It's convenient for separating this data fromt he source code.
CONFIG_FILE = 'deepstream-rtsp.cfg'

# Basic dependencies
import os
import time
import math


# Additional configuration is pulled from the process environment, if these
# variables are present. In some cases default values are provided to enable
# users to not have to set these if they just want to use standard values.
def get_from_env(v, d):
  if v in os.environ and '' != os.environ[v]:
    return os.environ[v]
  else:
    return d
CODEC = get_from_env('CODEC', 'H264') # Could also be 'H265'
BITRATE = get_from_env('BITRATE', '4000000')
RTSPINPUT = get_from_env('RTSPINPUT', '') # No default, so it's *REQUIRED*
RTSPOUTPUTPORTNUM = get_from_env('RTSPOUTPUTPORTNUM', '8554')
RTSPOUTPUTPATH = get_from_env('RTSPOUTPUTPATH', '/ds') # The output URL's path
ARCH = get_from_env('ARCH', '') # No default, so it's *REQUIRED*
IPADDR = get_from_env('IPADDR', '<IPADDRESS>') # host LAN IP, if given
SHOW_FRAMES = 'no' != get_from_env('SHOW_FRAMES', 'yes') # Default is to show
OUTPUT_WIDTH = int(get_from_env('OUTPUT_WIDTH', '1200')) # Output video width
OUTPUT_HEIGHT = int(get_from_env('OUTPUT_HEIGHT', '600')) # Output video height

RTSP_INPUTS = RTSPINPUT.split(',')

# The original examples require the code to be run fromn a specific
# directory, which is inconvenient and error-prone. So I am explicitly
# manipulating the search path here to remove the working directory
# dependency:
import sys
# Oddly the python3 lib is not on the search path, so add that first
sys.path.append('/usr/lib/python3.6')
if 'arm64' == ARCH or 'aarch64' == ARCH:
  # For NVIDIA Jetson (arm64) hosts, this path is needed:
  sys.path.append('/opt/nvidia/deepstream/deepstream-5.0/sources/python/bindings/jetson')
elif 'amd64' == ARCH or 'x86_64' == ARCH:
  # For x86 hosts with NVIDIA graphics cards, this path is needed:
  sys.path.append('/opt/nvidia/deepstream/deepstream-5.0/sources/python/bindings/x86_64')
else:
  sys.stderr.write('ERROR: Unsupported hardware architecture, "%s".\n' % ARCH)
  sys.exit(1)

# This path is required to enable the "common" files from the python bindings
sys.path.append('/opt/nvidia/deepstream/deepstream-5.0/sources/python/apps')
# And there's local stuff
sys.path.append('.')

# I switched the example to use standard temp files
import tempfile

# Gstreamer dependency
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GObject, Gst, GstRtspServer
from common.is_aarch_64 import is_aarch64
from common.bus_call import bus_call

# Import the NVIDIA Deepstream Python bindings
import pyds





#
# This is support code for the RTSP stream input element
# 
# The original example code is capable of receiving multiple video streams
# together, but here I'm just using a single stream input here..
#
# This code comes from:
#    /opt/nvidia/deepstream/deepstream-5.0/sources/python/apps/deepstream-imagedata-multistream
#
def cb_newpad(decodebin, decoder_src_pad, data):
    debug("In cb_newpad")
    caps=decoder_src_pad.get_current_caps()
    gststruct=caps.get_structure(0)
    gstname=gststruct.get_name()
    source_bin=data
    features=caps.get_features(0)

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
    if(gstname.find("video")!=-1):
        # Link the decodebin pad only if decodebin has picked nvidia
        # decoder plugin nvdec_*. We do this by checking if the pad caps contain
        # NVMM memory features.
        if features.contains("memory:NVMM"):
            # Get the source bin ghost pad
            bin_ghost_pad=source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write("ERROR: Failed to link decoder src pad to source bin ghost pad\n")
                sys.exit(1)
        else:
            sys.stderr.write("ERROR: Decodebin did not pick nvidia decoder plugin.\n")
            sys.exit(1)
def decodebin_child_added(child_proxy,Object,name,user_data):
    debug("Decodebin child added:" + name)
    if(name.find("decodebin") != -1):
        Object.connect("child-added",decodebin_child_added,user_data)
    if(is_aarch64() and name.find("nvv4l2decoder") != -1):
        debug("Seting bufapi_version")
        Object.set_property("bufapi-version",True)
def create_source_bin(index,uri):
    debug("Creating source bin")

    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name="source-bin-%02d" %index
    debug(bin_name)
    nbin=Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write("ERROR: Unable to create source bin")
        sys.exit(1)

    # Source element for reading from the uri.
    # We will use decodebin and let it figure out the container format of the
    # stream and the codec and plug the appropriate demux and decode plugins.
    uri_decode_bin=Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write("ERROR: Unable to create uri decode bin")
        sys.exit(1)
    # We set the input uri to the source element
    uri_decode_bin.set_property("uri",uri)
    # Connect to the "pad-added" signal of the decodebin which generates a
    # callback once a new pad for raw data has beed created by the decodebin
    uri_decode_bin.connect("pad-added",cb_newpad,nbin)
    uri_decode_bin.connect("child-added",decodebin_child_added,nbin)

    # We need to create a ghost pad for the source bin which will act as a proxy
    # for the video decoder src pad. The ghost pad will not have a target right
    # now. Once the decode bin creates the video decoder and generates the
    # cb_newpad callback, we will set the ghost pad target to the video decoder
    # src pad.
    Gst.Bin.add(nbin,uri_decode_bin)
    bin_pad=nbin.add_pad(Gst.GhostPad.new_no_target("src",Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write("ERROR: Failed to add ghost pad in source bin")
        sys.exit(1)
    return nbin





#
# This is the "PGIE" inferencing example from the original NVIDIA Deepstream
# example in 
#
# This example detects these classes:
#  - normal vehicles (cars, trucks, busses)
#  - 2-wheeled vehicles (bicycles, mopeds, motorcycles)
#  - people
#  - road signs
#
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3





#
# This function is the callback function we will attach to the probe.
# (see "probe" below for details).
#
# It will get called when data arrives at the sink (input) pad for the
# OSD element (the one that draws the boxes, and places text on the
# video frames). This is a good place to probe because all the information
# about the objects detected must be available here.
#
def osd_sink_pad_buffer_probe(pad,info,u_data):
    frame_number=0
    #Intiallizing object counter with 0.
    obj_counter = {
        PGIE_CLASS_ID_VEHICLE:0,
        PGIE_CLASS_ID_PERSON:0,
        PGIE_CLASS_ID_BICYCLE:0,
        PGIE_CLASS_ID_ROADSIGN:0
    }
    num_rects=0

    gst_buffer = info.get_buffer()
    if not gst_buffer:
        debug("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
            # The casting is done by pyds.NvDsFrameMeta.cast()
            # The casting also keeps ownership of the underlying memory
            # in the C code, so the Python garbage collector will leave
            # it alone.
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break

        frame_number=frame_meta.frame_num
        num_rects = frame_meta.num_obj_meta
        l_obj=frame_meta.obj_meta_list
        while l_obj is not None:
            try:
                # Casting l_obj.data to pyds.NvDsObjectMeta
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break
            obj_counter[obj_meta.class_id] += 1
            try: 
                l_obj=l_obj.next
            except StopIteration:
                break

        # Acquiring a display meta object. The memory ownership remains in
        # the C code so downstream plugins can still access it. Otherwise
        # the garbage collector will claim it when this probe function exits.
        display_meta=pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_labels = 1
        py_nvosd_text_params = display_meta.text_params[0]
        # Setting display text to be shown on screen
        # Note that the pyds module allocates a buffer for the string, and the
        # memory will not be claimed by the garbage collector.
        # Reading the display_text field here will return the C address of the
        # allocated string. Use pyds.get_string() to get the string content.
        py_nvosd_text_params.display_text = "Frame={}  Objects={}  Vehicles={}  Cycles={}  Persons={}  Signs={}".format(frame_number, num_rects, obj_counter[PGIE_CLASS_ID_VEHICLE], obj_counter[PGIE_CLASS_ID_BICYCLE], obj_counter[PGIE_CLASS_ID_PERSON], obj_counter[PGIE_CLASS_ID_ROADSIGN])

        # Now set the offsets where the string should appear
        py_nvosd_text_params.x_offset = 10
        py_nvosd_text_params.y_offset = 12

        # Font , font-color and font-size
        py_nvosd_text_params.font_params.font_name = "Serif"
        py_nvosd_text_params.font_params.font_size = 10
        # set(red, green, blue, alpha); set to White
        py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

        # Text background color
        py_nvosd_text_params.set_bg_clr = 1
        # set(red, green, blue, alpha); set to Black
        py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)
        # Using pyds.get_string() to get display_text as string
        if SHOW_FRAMES:
            print(pyds.get_string(py_nvosd_text_params.display_text))
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
        try:
            l_frame=l_frame.next
        except StopIteration:
            break
			
    return Gst.PadProbeReturn.OK	




##############################################################################
# The main program
##############################################################################
#
# Here the deepstream pipeline is constructed of "elements", and you may
# also optionally add "probes" to consume information at any point:
#
# <input> ---> element0 ---> element1 ---> ... -+-> elementN ---> <output>
#                                               |
#                                               V
#                                            (probe)
#
# Each element in the pipeline performs some kind of processing on the stream
# and each may have zero or more source pads and/or zero or more sink pads:
#
#             +-----------------------------------------------+
#             |                    elementX                   |
#             |                                               |
#             |            Some processing happens            |
#             |            here between the sink pads         |
#             |            and the source pads.               |
#             |                                               |
# <input0> ------> sinkpad0                     sourcepad0 ------> <output0>
#             |                                               |
# <input1> ------> sinkpad1                     sourcepad1 ------> <output1>
#             |                                               |
#   ...       |       ...                            ...      |     ...
#             |                                               |
# <inputN> ------> sinkpadN                     sourcepadN ------> <outputN>
#             |                                               |
#             +-----------------------------------------------+
#
# A "source element" typically starts a pipeline and has zero sink
# pads since it receives nothing from other pipeline elements, and it
# provides a single source pad which can feed data to other elements.
#
# A "sink element" typically ends a pipeline and as one sink pad (to
# receive data from the penultimate element) and provides no source
# pads for downstream elements (since there are none).
#
# Most other elements have a single sink pad for input and provide
# a single source pad for output. Multiplexor (mux) elements receive
# multiple inputs and produce a single output, so they have multiple
# sink pads and a single source pad. De-multiplexor (demux) elements
# perform the opposite function converting a single input on their
# only sink pad into multiple outputs on their source pads.
#
# In general elements are created with:
#    elementX = Gst.ElementFactory.make( ... )
# The resullt of that must be checked, e.g.:
#    if not elementX: sys.exit(1)
# Elements are often configured with:
#    elementX.set_property('property-name-goes-here', 'value goes here')
# When ready, elements are added to the pipeline:
#    pipeline.add(elementX)
# If the source pad of a previous element (elementQ here) needs to
# be linked to the sink pad of your element (elementX here) you can
# use the link function, like this:
#    elementQ.link(elementX)
# The result will flow data from elementQ to elementX:
#    elementQ -> elementX
#    
# NOTE: for the initial "source element" and the final "sink element", I
# have provided commented-out alternatives (e.g., file input, screen output,
# and no output (the "fake" sink). There is also a "fake" source available
# but I am not sure what use that has.
#

def main(args):

    # Announce some useful info at startup
    print('\n\n\n\n')
    print('Using codec: %s, and bitrate: %s' % (CODEC, BITRATE))
    print('RTSP input streams (%d):' % (len(RTSP_INPUTS)))
    for i in range(len(RTSP_INPUTS)):
        print('  %d: "%s"' % (i, RTSP_INPUTS[i]))
    print('RTSP output stream: "rtsp://%s:%s%s"' % (IPADDR, RTSPOUTPUTPORTNUM, RTSPOUTPUTPATH))
    print('\n\n\n\n')

    time.sleep(5)
    # Initialize GStreamer
    GObject.threads_init()
    Gst.init(None)

    # Create the GStreamer pipeline object that will connect the elements
    debug("Creating Pipeline ")
    pipeline = Gst.Pipeline()
    if not pipeline:
        sys.stderr.write("ERROR: Unable to create Pipeline\n")
        sys.exit(1)
    

    #########################################################################
    # The first "source element" in the pipeline is a "bin" element
    #########################################################################

    # NOTE: An alternate option here could be a file as an input source:
    #debug("Creating an element that uses a file as an input source")
    #source = Gst.ElementFactory.make("filesrc", "file-source")
    #if not source:
    #    sys.stderr.write("ERROR: Unable to create file input element!\n")
    #    sys.exit(1)
    
    # In this example I am using a list of one or more RTSP streams for input.
    # The code for this is mostly within these 3 functions above:
    #     def cb_newpad(decodebin, decoder_src_pad,data):
    #     def decodebin_child_added(child_proxy,Object,name,user_data):
    #     def create_source_bin(index,uri):
    # All of these functions were taken from this NVIDIA Deepstream example:
    #   /opt/nvidia/deepstream/deepstream-5.0/sources/python/apps/deepstream-imagedata-multistream
    # This element consumes RTSP streams "live", and multiplexes them
    # together before passing the *combined* stream on to the next element
    # in the pipeline. Each of these input RTSP streams is added to the
    # pipeline as a "bin", and all of them are linked to the streammux
    # element, something like this:
    #
    #  +-------------+   +-------------------+
    #  | stream0-bin +-->|sink-pad           |
    #  +-------------+   |                   |
    #                    |                   |
    #  +-------------+   |                   |
    #  | stream1-bin +-->|sink-pad           |   +--------------+
    #  +-------------+   |                   +-->| next-element +--> ...
    #                    | streammux-element |   +--------------+
    #         ...        |                   |
    #                    |                   |
    #  +-------------+   |                   |
    #  | streamN-bin +-->|sink-pad           |
    #  +-------------+   +-------------------+
    #

    # Multiplexing element with bins to read from multiple RTSP input streams
    debug("Creating elements to receive RTSP streams as the video input")

    # Create nvstreammux instance to form batches from one or more sources.
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write("ERROR: Unable to create NvStreamMux\n")
        sys.exit(1)
    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)

    # Add streammux to the pipeline
    pipeline.add(streammux)

    # Initialization
    parent_folder_name = tempfile.mkdtemp()
    frame_count = {}
    saved_count = {}

    # Loop through the provided RTSP input sources
    for i in range(len(RTSP_INPUTS)):

        name = RTSP_INPUTS[i]
        debug("--> input #%d: %s" % (i, name))

        # Init for this stream
        os.mkdir(parent_folder_name+"/stream_"+str(i))
        frame_count["stream_"+str(i)]=0
        saved_count["stream_"+str(i)]=0
        if name.find("rtsp://") == 0 :
            is_live = True

        # Create the bin for this stream, and make a source pad for its output
        source_bin=create_source_bin(i, name)
        if not source_bin:
            sys.stderr.write("ERROR: Unable to create source bin \n")
            sys.exit(1)
        srcpad=source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("ERROR: Unable to create src pad bin \n")
            sys.exit(1)

        # Add this bin to the pipeline
        pipeline.add(source_bin)

        # Get a sink pad in the streammux element
        padname="sink_%u" %i
        sinkpad= streammux.get_request_pad(padname)
        if not sinkpad:
            sys.stderr.write("ERROR: Unable to create sink pad bin \n")
            sys.exit(1)

        # Link the source pad on this bin to the sink pad in streammux
        srcpad.link(sinkpad)

    debug("All input source elements have been added to the pipeline")





    #########################################################################
    # The next element in the pipeline does the inferencing (on the GPU)
    #########################################################################
    
    debug("Creating an element to do inferencing (PGIE, nvinfer)")

    # Use nvinfer to run inferencing on decoder's output,
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    if not pgie:
        sys.stderr.write("ERROR: Unable to create pgie\n")
        sys.exit(1)

    # The configuration for the inferencing comes from the CONFIG_FILE.
    # See "CONFIG_FILE" above for details
    pgie.set_property('config-file-path', CONFIG_FILE)

    # Add PGIE to the pipeline, then link streammuux to its input
    pipeline.add(pgie)
    streammux.link(pgie)
    debug("The PGIE element has been added to the pipeline, and linked")
    




    #########################################################################
    # The next element in the pipeline converts the output to RGBA format
    #########################################################################

    debug("Creating an element that converts output video to RGBA format")

    # Use convertor to convert from NV12 to RGBA as required by nvosd
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
    if not nvvidconv:
        sys.stderr.write("ERROR: Unable to create nvvidconv\n")
        sys.exit(1)
    
    # Add the convertor to the pipeline, then link pgie to its input
    pipeline.add(nvvidconv)
    pgie.link(nvvidconv)
    debug("The convertor element has been added to the pipeline, and linked")






    #########################################################################
    # At this point in the pipeline, add a "probe" on the `nvvidconv` input
    #########################################################################

    debug("Creating a probe to view the inferencing metadata")

    # This probe will consume the meta data generated by nvinfer
    # and provide it to OSD later.
    # The probe is added to the sink pad of the OSD element that
    # follows nvinfer (so it has all object detection metadata).
    # That element is nvvidconv:
    followingsinkpad = nvvidconv.get_static_pad("sink")
    if not followingsinkpad:
        sys.stderr.write("ERROR: Unable to get sink pad of nvosd\n")
        sys.exit(1)
    # Attach a callback function to receive the data from this probe
    # The probe's callback function displays in the terminal the object
    # detection results metadata for each frame.
    # See the "osd_sink_pad_buffer_probe" function definition above for
    # details on how the probe receives the data and what it does with it.
    followingsinkpad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)
    





    #########################################################################
    # Next element de-multiplexes the input streams into tiles in one stream
    #########################################################################

    debug("Creating an element to demultiplex the videos into tiles")

    number_of_sources = len(RTSP_INPUTS)
    tiler=Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
    if not tiler:
        sys.stderr.write(" Unable to create tiler \n")
    tiler_rows=int(math.sqrt(number_of_sources))
    tiler_columns=int(math.ceil((1.0*number_of_sources)/tiler_rows))
    tiler.set_property("rows",tiler_rows)
    tiler.set_property("columns",tiler_columns)
    tiler.set_property("width", OUTPUT_WIDTH)
    tiler.set_property("height",OUTPUT_HEIGHT)
    if not is_aarch64():
        # Use CUDA unified memory in the pipeline so frames
        # can be easily accessed on CPU in Python.
        mem_type = int(pyds.NVBUF_MEM_CUDA_UNIFIED)
        streammux.set_property("nvbuf-memory-type", mem_type)
        nvvidconv.set_property("nvbuf-memory-type", mem_type)
        nvvidconv1.set_property("nvbuf-memory-type", mem_type)
        tiler.set_property("nvbuf-memory-type", mem_type)
    pipeline.add(tiler)
    nvvidconv.link(tiler)
    debug("The demultiplexing/tiling element was added and linked")






    #########################################################################
    # The next element in the pipeline draws boxes (requires RGBA input)
    #########################################################################

    debug("Creating elements that draw boxes in the output video")

    # Create OSD to draw on the converted RGBA buffer
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    if not nvosd:
        sys.stderr.write("ERROR: Unable to create nvosd\n")
        sys.exit(1)
    nvvidconv_postosd = Gst.ElementFactory.make("nvvideoconvert", "convertor_postosd")
    if not nvvidconv_postosd:
        sys.stderr.write("ERROR: Unable to create nvvidconv_postosd\n")
        sys.exit(1)
    
    # Add the two OSD elements to the pipeline, then link them togther and to the convertor
    pipeline.add(nvosd)
    pipeline.add(nvvidconv_postosd)
    tiler.link(nvosd)
    nvosd.link(nvvidconv_postosd)
    debug("The OSD element has been added to the pipeline, and linked")






    #########################################################################
    # The next element in the pipeline is a caps filter
    #########################################################################

    debug("Creating a caps filter element (to enforce data format restrictions to help maintain stream consistency and processing efficiency)")

    # Create a caps filter
    caps = Gst.ElementFactory.make("capsfilter", "filter")
    caps.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))
    
    # Add the caps filter to the pipeline, then link the OSD output to its input
    pipeline.add(caps)
    nvvidconv_postosd.link(caps)
    debug("The caps filter element has been added to the pipeline, and linked")





    #########################################################################
    # The next element in the pipeline encodes the output (v4l2, h264)
    #########################################################################

    debug("Creating an element that converts output video to H264 for 4VL2")

    # Make the encoder
    if CODEC == "H264":
        encoder = Gst.ElementFactory.make("nvv4l2h264enc", "encoder")
        debug("Creating H264 Encoder")
    elif CODEC == "H265":
        encoder = Gst.ElementFactory.make("nvv4l2h265enc", "encoder")
        debug("Creating H265 Encoder")
    if not encoder:
        sys.stderr.write("ERROR: Unable to create encoder")
        sys.exit(1)
    encoder.set_property('bitrate', int(BITRATE))
    if is_aarch64():
        encoder.set_property('preset-level', 1)
        encoder.set_property('insert-sps-pps', 1)
        encoder.set_property('bufapi-version', 1)
    
    # Add the V$L2/H264 encoder element to the pipeline, then link the caps filter to it
    pipeline.add(encoder)
    caps.link(encoder)
    debug("The encoder element has been added to the pipeline, and linked")






    #########################################################################
    # The next element in the pipeline encodes the output into RTP packets
    #########################################################################

    debug("Creating an element that encapsulates video into RTP packets for RTSP streaming")

    # Make the payload-encode video into RTP packets
    if CODEC == "H264":
        rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay")
        debug("Creating H264 rtppay")
    elif CODEC == "H265":
        rtppay = Gst.ElementFactory.make("rtph265pay", "rtppay")
        debug("Creating H265 rtppay")
    if not rtppay:
        sys.stderr.write("ERROR: Unable to create rtppay")
        sys.exit(1)

    # Add the RTP packet encoder element to the pipeline, then link the H264 encoder onto it
    pipeline.add(rtppay)
    encoder.link(rtppay)
    debug("The RTP packet encoder element has been added to the pipeline, and linked")






    #########################################################################
    # The final "sink element" in the pipeline is the RTSP output stream sink
    #########################################################################

    # As an alternative, you could send the output nowhere (the "fake" sink)
    #debug("Creating FAKE sink")
    #sink = Gst.ElementFactory.make("fakesink", "nvvideo-renderer")
    #if not sink:
    #    sys.stderr.write("ERROR: Unable to create FAKE sink\n")
    #    sys.exit(1)
    #sink.set_property("sync", 0)

    # As an alternative, you could send the output to the screen
    #debug("Creating EGLSink")
    #sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
    #if not sink:
    #    sys.stderr.write("ERROR: Unable to create egl sink\n")
    #    sys.exit(1)
    #sink.set_property("sync", 0)

    debug("Creating RTSP output stream sink...")

    # The RTSP stream output sink sends to this local multicast UDP port
    # This is received by the GstRtspStreamer instance created below once
    # the pipeline is started. See "GstRtspStreamer" below for details.
    UDP_MULTICAST_ADDRESS = '224.224.255.255'
    UDP_MULTICAST_PORT = 5400
    sink = Gst.ElementFactory.make("udpsink", "udpsink")
    if not sink:
        sys.stderr.write("ERROR: Unable to create udpsink")
        sys.exit(1)
    sink.set_property('host', UDP_MULTICAST_ADDRESS)
    sink.set_property('port', UDP_MULTICAST_PORT)
    sink.set_property('async', False)

    # The command below tells it to sync to a clock (1) or don't sync (0).
    # I find that using 1 slows things down, but it seems much more regular.
    # When I use 0 it is much faster but it freezes intermittently.
    sink.set_property("sync", 0)
    
    # Add the RTSP output stream sink element to the pipeline, then link the RTP paket encoder onto it
    pipeline.add(sink)
    rtppay.link(sink)
    debug("The RTSP output stream element has been added to the pipeline, and linked")






    #########################################################################
    # Pipeline construction is complete! Create the event loop.
    #########################################################################

    # create an event loop and feed gstreamer bus mesages to it
    debug("Creating the event loop...")
    loop = GObject.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect ("message", bus_call, loop)
    





    #########################################################################
    # Create a GstRtspStreamer instance to consume the video stream from the
    # multicast UDP port (see "MULTICAST" for details). This insttance will
    # publish an RTSP output stream on the specified (TCP) port. Since this
    # example is running in a container you will typically want to publish
    # this TCP port to the host, so users can access the RTSP stream from
    # other hosts.
    #########################################################################

    server = GstRtspServer.RTSPServer.new()
    server.props.service = RTSPOUTPUTPORTNUM
    server.attach(None)
    
    factory = GstRtspServer.RTSPMediaFactory.new()
    factory.set_launch( "( udpsrc name=pay0 port=%d buffer-size=524288 caps=\"application/x-rtp, media=video, clock-rate=90000, encoding-name=(string)%s, payload=96 \" )" % (UDP_MULTICAST_PORT, CODEC))
    factory.set_shared(True)
    server.get_mount_points().add_factory(RTSPOUTPUTPATH, factory)
    debug("RTSP output stream service is ready")




    
    #########################################################################
    # Finally we can start it running...
    #########################################################################

    # Start play back and listen to events
    print("\n\n\n\n*** Deepstream RTSP pipeline example is starting...\n\n\n\n")
    pipeline.set_state(Gst.State.PLAYING)
    try:
        # Run forever
        loop.run()
    except:
        sys.stderr.write("\n\n\n*** ERROR: main event loop exited!\n\n\n")

    # Attempt cleanup on error
    pipeline.set_state(Gst.State.NULL)





if __name__ == '__main__':
    sys.exit(main(sys.argv))

