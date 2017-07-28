Extension to recipetool to enable automatic creation of 
BitBake recipe files for ROS packages.

## USAGE ##

  Initialize the build environment:

    source oe-init-build-env

  Currently the plugin only allow for processing a single
  ROS package in a repository. If a repository contains more than
  one package, or the package is not in the root of the repository,
  then use the `--src-subdir=<dir>` option.

  ROS repositories generally do not use `master` as their default 
  branch, so be sure to include the correct branch for the desired
  distribution as part of the URI: `<URI>;branch=indigo-devel`

```
devtool add --src-subdir=ros_comm "https://github.com/ros/ros_comm.git;branch=indigo-devel"
```

## TO DO ##

  * Generate recipes for each package in a repository.
  * Add support for ament for ROS2 packages.
  * Wrapper for using rosdistro data to generate recipes for various ROS distributions.

