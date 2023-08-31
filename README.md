# Stabbie 🔪
A friendly `fstab` auto-mount script for remote filesystems

## ⚠️ Disclaimer  
This is a Work-In-Progress side-project, **do not use stabbie with critical data or systems**.

<!-- Icon goes here -->

## ✨ Features
* **Discover entries** with remote filesystems from the fstab
* **Mount entries** when their file server is reachable
* **Unmount entries** when their file server is away

## ✏️ Example situation
- On your LAN, there is a NAS at `192.168.1.50`
- This NAS exposes NFS shares
- You have a personnal VPN that connects to your LAN
- Your fstab specifies mount points and options for the NFS shares
```
192.168.1.50:/share1 /mnt/share1 nfs x-stabbie,noauto,_netdev 0 0
192.168.1.50:/share2 /mnt/share2 nfs x-stabbie,noauto,_netdev 0 0
192.168.1.50:/share3 /mnt/share3 nfs x-stabbie,noauto,_netdev 0 0
```

You want to try to mount the shares only when the server is reachable.  
So, when you're home or when you connect to the VPN.

You just have to run `stabbie` when the network status changes to automatically mount or unmount the shares depending on the situation.

## 🔧 Installation and Usage

### Prerequisites
* Linux environment
* fstab at `/etc/fstab`
* Python 3.11 or newer

### `fstab` structure
Stabbie only mounts and unmounts fstab entries:
* Marked with the option `x-stabbie`
* Of the [supported filesystem types](#-supported-filesystem-types)

### Installation

Install from source
```
pip install git+https://github.com/GeoffreyCoulaud/stabbie.git
```

### Usage

`stabbie` needs root privileges to mount and unmount.

Basic usage:
```
stabbie
```

You can get an up to date list of arguments from the integrated help:
```
stabbie --help
```


## 📁 Supported filesystem types

* NFS

Feel free to open an issue or a pull request to add support for more filesystems