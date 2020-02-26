# Lint as: python3
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Helper functions for computing gradients."""


import functools

import tensorflow.compat.v2 as tf
from tensorflow_probability.python.math import value_and_gradient


def fwd_gradient(func, x, input_gradients=None, use_gradient_tape=False):
  """Computes forward mode gradient.

  Implementation based on suggestions in
  [this thread](https://github.com/tensorflow/tensorflow/issues/19361).

  TensorFlow computes gradients using the reverse mode automatic
  differentiation which is suitable for typical machine learning situations
  where one has a scalar loss function that one wants to differentiate with
  respect to the parameters. In some cases, one needs to be able to compute
  directional derivatives of non-scalar functions. Suppose F is a function from
  R^n to R^m and let u be a fixed vector in R^n, w a fixed vector in R^m and
  x a variable taking values in R^n. Let J(F) denote the jacobian matrix of
  F of shape [m, n] (i.e. J(F)[i, j] = dF_i / dx_j). Then the default
  gradients function in TF computes the expression
  w^T.J(F) (i.e. Sum[w_i dF_i / dx_j, 1 <= i <= m]).

  On the other hand, one also often needs to compute the directional derivative
  J(F).u (i.e. Sum[u_j dF_i / dx_j, 1 <= j <= n]). Unfortunately, TensorFlow
  has no native support for accumulating this. Providing first class support
  for forward mode differentiation requires some significant changes in the core
  architecture of TF (including writing a directional derivative for each
  op).

  The following function sidesteps this by using two passes of reverse mode
  differentiation. Mathematically, the idea is simple. If F: R^n -> R^m, then
  w^T.J(F) seen as a function of w is a function from R^m to R^n (because
  w is in R^m, and w^T.J(F) is in R^n). Hence a reverse mode differentiation
  with respect to w should produce J(F).u.

  This function provides only a small subset of the flexibility of
  the tf.gradients function. This may be extended in the future.

  ### Example

  Following example demonstrates the usage and the difference between this
  op and the standard `tf.gradients`
  ```python
    t = tf.range(1, 3, dtype=tf.float32)  # Shape [2]
    def fn(t):
      return tf.stack([t, t ** 2, t ** 3], axis=0)  # Shape [3, 2]
    # Produces shape [3, 2] with values [[1, 1], [2, 4], [3, 12]]
    fwd_grad_y = fwd_gradient(fn, t)
    # Produces shape [2] with values [6, 17].
    bck_grad_y = tf.gradients(y, t)[0]
  ```

  Args:
    func: A Python callable accepting one `Tensor` of shape of `x` and returning
      a `Tensor` of any shape. The function whose gradient is to be computed.
    x: A `Tensor` with respect to which the gradient is to be computed.
    input_gradients: A `Tensor` of the same shape as `x`. The direction along
      which the directional derivative is to be computed.
      Default value: `None` which maps to a ones-like `Tensor` of `x`.
    use_gradient_tape: Optional Python bool. Whether to use gradient tape even
      when eager mode is not turned on.
      Defaule value: `False`.

  Returns:
    A `Tensor` of the same shape as `func(x)`.
  """
  if not tf.executing_eagerly() and not use_gradient_tape:
    y = func(x)
    w = tf.zeros_like(y)
    g = tf.gradients(y, x, grad_ys=w)
    return tf.gradients(g, w, grad_ys=input_gradients)[0]

  with tf.GradientTape() as outer_tape:
    with tf.GradientTape() as inner_tape:
      inner_tape.watch(x)
      y = func(x)
    w = tf.zeros_like(y)
    outer_tape.watch(w)
    g = inner_tape.gradient(y, x, output_gradients=w)
  return outer_tape.gradient(g, w, output_gradients=input_gradients)


def gradients(f, xs, output_gradients=None, use_gradient_tape=False, name=None):
  """Computes the gradients of `f` wrt to `*xs`.

  Args:
    f: Python `callable` to be differentiated.
    xs: Python list of parameters of `f` for which to differentiate. (Can also
      be single `Tensor`.)
    output_gradients: A `Tensor` or list of `Tensor`s the same size as the
      result `ys = f(*xs)` and holding the gradients computed for each `y` in
      `ys`. This argument is forwarded to the underlying gradient implementation
      (i.e., either the `grad_ys` argument of `tf.gradients` or the
      `output_gradients` argument of `tf.GradientTape.gradient`).
      Default value: `None` which maps to a ones-like `Tensor` of `ys`.
    use_gradient_tape: Python `bool` indicating that `tf.GradientTape` should be
      used regardless of `tf.executing_eagerly()` status.
      Default value: `False`.
    name: Python `str` name prefixed to ops created by this function.
      Default value: `None` (i.e., `'gradients'`).

  Returns:
    A `Tensor` with the gradient of `y` wrt each of `xs`.
  """
  _, grad = value_and_gradient(
      f, xs, output_gradients=output_gradients,
      use_gradient_tape=use_gradient_tape, name=name or 'gradients')
  return grad


def make_val_and_grad_fn(value_fn):
  """Function decorator to compute both function value and gradient.

  For example:

  ```
  @tff.math.make_val_and_grad_fn
  def quadratic(x):
    return tf.reduce_sum(scales * (x - minimum) ** 2, axis=-1)
  ```

  Turns `quadratic` into a function that accepts a point as a `Tensor` as input
  and returns a tuple of two `Tensor`s with the value and the gradient of the
  defined quadratic function evaluated at the input point.

  This is useful for constucting functions to optimize with tff.math.optimizer
  methods.

  Args:
    value_fn: A python function to decorate.

  Returns:
    The decorated function.
  """
  @functools.wraps(value_fn)
  def val_and_grad(x):
    return value_and_gradient(value_fn, x)

  return val_and_grad
