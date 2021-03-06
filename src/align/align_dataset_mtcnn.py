"""Performs face alignment and stores face thumbnails in the output directory."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from scipy import misc
import sys
import os
import argparse
import random
import tensorflow as tf
import numpy as np
import facenet
import src.align.detect_face

def main(args):
    output_dir = os.path.expanduser(args.output_dir)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    # Store some git revision info in a text file in the log directory
    src_path,_ = os.path.split(os.path.realpath(__file__))
    facenet.store_revision_info(src_path, output_dir, ' '.join(sys.argv))
    dataset = facenet.get_dataset(args.input_dir)
    random.shuffle(dataset)
    
    print('Creating networks and loading parameters')    
    with tf.Graph().as_default():
        sess = tf.Session()
        with sess.as_default():
            with tf.variable_scope('pnet'):
                data = tf.placeholder(tf.float32, (None,None,None,3), 'input')
                pnet = src.align.detect_face.PNet({'data':data})
                pnet.load('../../data/det1.npy', sess)
            with tf.variable_scope('rnet'):
                data = tf.placeholder(tf.float32, (None,24,24,3), 'input')
                rnet = src.align.detect_face.RNet({'data':data})
                rnet.load('../../data/det2.npy', sess)
            with tf.variable_scope('onet'):
                data = tf.placeholder(tf.float32, (None,48,48,3), 'input')
                onet = src.align.detect_face.ONet({'data':data})
                onet.load('../../data/det3.npy', sess)
                
            pnet_fun = lambda img : sess.run(('pnet/conv4-2/BiasAdd:0', 'pnet/prob1:0'), feed_dict={'pnet/input:0':img})
            rnet_fun = lambda img : sess.run(('rnet/conv5-2/conv5-2:0', 'rnet/prob1:0'), feed_dict={'rnet/input:0':img})
            onet_fun = lambda img : sess.run(('onet/conv6-2/conv6-2:0', 'onet/conv6-3/conv6-3:0', 'onet/prob1:0'), feed_dict={'onet/input:0':img})
    
    minsize = 20 # minimum size of face
    threshold = [ 0.6, 0.7, 0.7 ]  # three steps's threshold
    factor = 0.709 # scale factor
    
    # Scale the image such that the face fills the frame when cropped to crop_size
    nrof_images_total = 0
    nrof_prealigned_images = 0
    nrof_successfully_aligned = 0
    for cls in dataset:
        output_class_dir = os.path.join(output_dir, cls.name)
        if not os.path.exists(output_class_dir):
            os.makedirs(output_class_dir)
        random.shuffle(cls.image_paths)
        for image_path in cls.image_paths:
            nrof_images_total += 1
            filename = os.path.splitext(os.path.split(image_path)[1])[0]
            output_filename = os.path.join(output_class_dir, filename+'.png')
            if not os.path.exists(output_filename):
                try:
                    img = misc.imread(image_path)
                except (IOError, ValueError, IndexError) as e:
                    errorMessage = '{}: {}'.format(image_path, e)
                    print(errorMessage)
                else:
                    if img.ndim == 2:
                        img = facenet.to_rgb(img)

                    bounding_boxes, _ = src.align.detect_face.detect_face(img, minsize, pnet_fun, rnet_fun, onet_fun, threshold, factor)
                    nrof_faces = bounding_boxes.shape[0]
                    if nrof_faces>0:
                        det = bounding_boxes[:,0:4]
                        img_size = np.asarray(img.shape)[0:2]
                        if nrof_faces>1:
                            bounding_box_size = (det[:,2]-det[:,0])*(det[:,3]-det[:,1])
                            img_center = img_size / 2
                            offsets = np.vstack([ (det[:,0]+det[:,2])/2-img_center[0], (det[:,1]+det[:,3])/2-img_center[1] ])
                            offset_dist_squared = np.sum(np.power(offsets,2.0),0)
                            index = np.argmax(bounding_box_size-offset_dist_squared*2.0) # some extra weight on the centering
                            det = det[index,:]
                        det = np.squeeze(det)
                        bb = np.zeros(4, dtype=np.int32)
                        bb[0] = np.maximum(det[0]-args.margin/2, 0)
                        bb[1] = np.maximum(det[1]-args.margin/2, 0)
                        bb[2] = np.minimum(det[2]+args.margin/2, img_size[0])
                        bb[3] = np.minimum(det[3]+args.margin/2, img_size[1])
                        cropped = img[bb[1]:bb[3],bb[0]:bb[2],:]
                        scaled = misc.imresize(cropped, (args.image_size, args.image_size), interp='bilinear')
                        print(image_path)
                        nrof_successfully_aligned += 1
                        misc.imsave(output_filename, scaled)
                    else:
                        print('Unable to align "%s"' % image_path)
                            
    print('Total number of images: %d' % nrof_images_total)
    print('Number of successfully aligned images: %d' % nrof_successfully_aligned)
    print('Number of pre-aligned images: %d' % nrof_prealigned_images)
            

def parse_arguments(argv):
    parser = argparse.ArgumentParser()
    
    parser.add_argument('input_dir', type=str, help='Directory with unaligned images.')
    parser.add_argument('output_dir', type=str, help='Directory with aligned face thumbnails.')
    parser.add_argument('--image_size', type=int,
        help='Image size (height, width) in pixels.', default=182)
    parser.add_argument('--margin', type=int,
        help='Margin for the crop around the bounding box (height, width) in pixels.', default=12)
    return parser.parse_args(argv)

if __name__ == '__main__':
    main(parse_arguments(sys.argv[1:]))
