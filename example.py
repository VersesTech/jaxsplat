import jaxsplat
import jax
import jax.numpy as jnp
import numpy as np
import imageio.v3 as iio
import optax


def main():
    key = jax.random.key(0)
    iterations = 200
    num_points = 1_000
    gt_path = "test.png"
    out_path = "out.png"
    lr = 0.05

    gt = jnp.array(iio.imread(gt_path)).astype(jnp.float32) / 255

    key, subkey = jax.random.split(key)
    params, coeffs = init(subkey, num_points, gt.shape[:2])

    optim = optax.adam(lr)
    optim_state = optim.init(params)

    def loss_fn(params, coeffs, gt):
        output = render_fn(params, coeffs)
        # loss = jnp.mean(optax.l2_loss(output, gt))
        loss = jnp.mean(jnp.square(output - gt))
        return loss

    with iio.imopen("out.mp4", "w", plugin="pyav") as video:
        video.init_video_stream("h264")
        for i in range(iterations):
            img = (render_fn(params, coeffs) * 255).astype(jnp.uint8)
            video.write_frame(img)

            loss, grads = jax.value_and_grad(loss_fn, argnums=0)(params, coeffs, gt)
            updates, optim_state = optim.update(grads, optim_state)
            params = optax.apply_updates(params, updates)
            print(f"{i=} {loss.item():.5f}")

            # print("means3d", params["means3d"].min(), params["means3d"].max())
            # print("scales", params["scales"].min(), params["scales"].max())
            # print("quats", params["quats"].min(), params["quats"].max())
            # print("colors", params["colors"].min(), params["colors"].max())
            # print("opacities", params["opacities"].min(), params["opacities"].max())

            # if loss < 1e-6:
            #     break

            # key, subkey = jax.random.split(key)
            # params, coeffs = init(subkey, num_points, (gt.shape[1], gt.shape[0]))

    out = render_fn(params, coeffs)
    iio.imwrite(out_path, (out * 255).astype(jnp.uint8))


def init(key, num_points, img_shape):
    key, subkey = jax.random.split(key)
    means3d = jax.random.uniform(
        subkey,
        (num_points, 3),
        minval=jnp.array([-2, -2, -1]),
        maxval=jnp.array([2, 2, 1]),
        dtype=jnp.float32,
    )

    key, subkey = jax.random.split(key)
    scales = jax.random.uniform(
        subkey, (num_points, 3), dtype=jnp.float32, minval=0, maxval=0.5
    )

    key, subkey = jax.random.split(key)
    u, v, w = jax.random.uniform(subkey, (3, num_points, 1))
    # quats = jax.ra  ndom.normal(subkey, (num_points, 4), dtype=jnp.float32)
    # quats /= jnp.linalg.norm(quats, axis=-1, keepdims=True)
    quats = jnp.hstack(
        [
            jnp.sqrt(1 - u) * jnp.sin(2 * jnp.pi * v),
            jnp.sqrt(1 - u) * jnp.cos(2 * jnp.pi * v),
            jnp.sqrt(u) * jnp.sin(2 * jnp.pi * w),
            jnp.sqrt(u) * jnp.cos(2 * jnp.pi * w),
        ]
    )

    viewmat = jnp.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 8.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )

    key, subkey = jax.random.split(key)
    colors = jax.random.uniform(subkey, (num_points, 3), dtype=jnp.float32)

    key, subkey = jax.random.split(key)
    opacities = jax.random.uniform(subkey, (num_points, 1), minval=0.5)

    background = jnp.array([0, 0, 0], dtype=jnp.float32)

    H, W = img_shape
    fx, fy = W / 2, H / 2
    cx, cy = W / 2, H / 2
    glob_scale = 1
    clip_thresh = 0.01
    block_size = 16

    return (
        {
            "means3d": means3d,
            "scales": scales,
            "quats": quats,
            "colors": colors,
            "opacities": opacities,
        },
        {
            "viewmat": viewmat,
            "background": background,
            "img_shape": img_shape,
            "f": (fx, fy),
            "c": (cx, cy),
            "glob_scale": glob_scale,
            "clip_thresh": clip_thresh,
            "block_size": block_size,
        },
    )


def render_fn(params, coeffs):
    means3d = params["means3d"]
    quats = params["quats"] / (
        jnp.linalg.norm(params["quats"], axis=-1, keepdims=True) + 1e-6
    )
    scales = params["scales"]
    colors = jax.nn.sigmoid(params["colors"])
    opacities = jax.nn.sigmoid(params["opacities"])

    (xys, depths, radii, conics, num_tiles_hit, cum_tiles_hit) = jaxsplat.project(
        means3d,
        scales,
        quats,
        coeffs["viewmat"],
        img_shape=coeffs["img_shape"],
        f=coeffs["f"],
        c=coeffs["c"],
        glob_scale=coeffs["glob_scale"],
        clip_thresh=coeffs["clip_thresh"],
        block_width=coeffs["block_size"],
    )

    img = jaxsplat.rasterize(
        colors,
        opacities,
        coeffs["background"],
        xys,
        depths,
        radii,
        conics,
        cum_tiles_hit,
        img_shape=coeffs["img_shape"],
        block_width=coeffs["block_size"],
    )

    return img


if __name__ == "__main__":
    main()
