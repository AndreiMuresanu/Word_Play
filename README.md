# word_play
A package for creating text-based environments.

# Quick Start

## Simple Example

```
pip install -e .
python examples/test_env_2.py
```

# Setup:

## Package Install
Install the package using this command from inside THIS directory:
```
pip install -e .
```

## Python Version
This package requires Python 3.13. It only requires 3.13 because it uses a couple of new type hint features. These are
minor and can easily be removed to drop the version requirement to 3.5, as this is the first version to introduce type
hints. If type hints are removed, the version requirement can be dropped even further.

## Package Requirements
The requirements.txt is not wrong; no additional packages are required.
The only exception is that if you wish to use some of the preset Model classes, you must install packages such as openai.
