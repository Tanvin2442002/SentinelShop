FROM ubuntu:24.04
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv openssh-server sudo python3 ufw acl iptables postgresql-client ca-certificates && rm -rf /var/lib/apt/lists/* && mkdir -p /run/sshd
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
