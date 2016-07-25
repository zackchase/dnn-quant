# Copyright 2016 Euclidean Technologies Management LLC All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import time
import os
import sys
import copy

import numpy as np
import tensorflow as tf

import model_utils
import configs

from tensorflow.python.platform import gfile
from batch_generator import BatchGenerator

def run_epoch(session, mdl, batches, eval_op, passes=1, eval_all=True,
                verbose=False):
  """Runs the model on the given data."""
  num_steps = batches.num_steps
  start_time = time.time()
  costs = 0.0
  errors = 0.0
  count = 0
  dot_count = 0
  prog_int = passes*num_steps/100 # progress interval for stdout
  predata = False
  
  if not num_steps > 0:
    raise RuntimeError("batch_size*num_unrollings is larger "
                         "than the training set size.")
  # print("num_steps = ",num_steps)
  # print("data_points = ",batches.num_data_points())
  # print("batch_size = ",mdl.batch_size)
  # print("unrollings = ",mdl.num_unrollings)

  batches.rewind_cursor()

  for _ in range(passes):

    for step in range(num_steps):

      #if eval_all is False:
      #  predata = batches.is_predata(FLAGS.min_history)

      x_batches, y_batches, seq_lengths, reset_flags = batches.next()
      
      cost, error, state, predictions = mdl.step( session, eval_op,
                                                    x_batches, y_batches,
                                                    seq_lengths, reset_flags )
      if not predata:
        costs  += cost
        errors += error
        count  += 1
      if ( verbose and ((prog_int<=1) or (step % (int(prog_int)+1)) == 0) ):
        dot_count += 1
        print('.',end='')
        sys.stdout.flush()

  if verbose:
    print("."*(100-dot_count),end='')
    print(" evals: %d (of %d), speed: %.0f seconds"%
            (count * mdl.batch_size * mdl.num_unrollings,
               passes * num_steps * mdl.batch_size * mdl.num_unrollings,
                  (time.time() - start_time) ) )
  sys.stdout.flush()

  return np.exp(costs / count), (errors / count)

def main(_):

  config = configs.get_configs()

  train_batches = BatchGenerator(config.train_datafile,
                                   config.key_name,
                                   config.target_name,
                                   config.num_inputs, config.num_outputs,
                                   config.batch_size, config.num_unrollings )

  valid_batches = BatchGenerator(config.valid_datafile,
                                   config.key_name,
                                   config.target_name,                                   
                                   config.num_inputs, config.num_outputs,
                                   config.batch_size, config.num_unrollings )
  
  tf_config = tf.ConfigProto( allow_soft_placement=True, 
                              log_device_placement=False )

  with tf.Graph().as_default(), tf.Session(config=tf_config) as session:

    mtrain, mvalid = model_utils.get_training_models(session, config, verbose=True)
    
    lr = config.initial_learning_rate
    perf_history = list()
    
    for i in range(config.max_epoch):

      lr = model_utils.adjust_learning_rate(session,
                                              config,
                                              mtrain,
                                              lr,
                                              perf_history )

      train_xentrop, train_error = run_epoch(session,
                                                  mtrain, train_batches,
                                                  mtrain.train_op,
                                                  passes=config.passes,
                                                  eval_all=True,
                                                  verbose=True)

      valid_xentrop, valid_error = run_epoch(session,
                                                  mvalid, valid_batches,
                                                  tf.no_op(),
                                                  passes=1,
                                                  eval_all=False,
                                                  verbose=True)
      
      print( ('Epoch: %d XEntrop: %.6f %.6f'
              ' Error: %.6f %.6f Learning rate: %.3f') % 
            (i + 1, 
             train_xentrop, valid_xentrop, train_error, valid_error, lr) )
      sys.stdout.flush()

      perf_history.append( train_xentrop )
      
      checkpoint_path = os.path.join(config.model_dir, "training.ckpt" )
      tf.train.Saver().save(session, checkpoint_path, global_step=i)
      
      # If train and valid are the same data then this is a test to make
      # sure that the model is producing the same error on both. Note,
      # however, that if keep_prob < 1 then the train model is probabilistic
      # and so these can only be approx equal.
      if (False):
        check_xentrop, check_error = run_epoch(session,
                                                    mtrain, train_batches,
                                                    tf.no_op(),
                                                    passes=1,
                                                    eval_all=False,
                                                    verbose=True)
        print("Check: %d XEntrop: %.2f =? %.2f Error: %.6f =? %.6f " %
                (i + 1, check_xentrop, valid_xentrop, check_error, valid_error))
        sys.stdout.flush()

if __name__ == "__main__":
  tf.app.run()