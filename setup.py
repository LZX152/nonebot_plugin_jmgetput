from setuptools import setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="nonebot_plugin_jmgetput",
    version="1.0.5",
    author="Llli",
    author_email="1712616512@qq.com",
    description="A plugin based on NoneBot2 to upload jmcomic files or files in qq group.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="",
    project_urls={
        "Bug Tracker": "",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    packages=["nonebot_plugin_jmgetput"],
    python_requires=">=3.7",
    install_requires=[
        "nonebot2 >= 2.0.0b2",
        "nonebot-adapter-onebot >= 2.0.0b1",
        'requests>=2.28.1'
    ],
)
