from setuptools import setup, find_packages

setup(
    name="proxychecker",
    version="1.0.0",
    description="Official ProxyChecker Python SDK",
    author="kaliptoz",
    url="https://github.com/kaliptoz/proxychecker-python",
    packages=find_packages(),
    install_requires=["requests>=2.28.0"],
    python_requires=">=3.8",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
)
