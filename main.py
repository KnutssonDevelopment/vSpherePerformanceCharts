import atexit
import ssl

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import matplotlib
import matplotlib.pyplot as plt
from variables import password_file

matplotlib.use("Qt5Agg")

VCENTER_HOST = "osi10192.im.dom"
VCENTER_USER = "admxbrkn@im.dom"

ESXI_HOSTS = [
    "osi10011.im.dom",
    "osi10012.im.dom",
    "osi10013.im.dom",
    "osi10014.im.dom"
]

NIC_LIST = ['vmnic4', 'vmnic5']


def get_password_from_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        password = f.read().strip()

    return password


def get_si_instance(host, user, pwd, port=443, disable_ssl_verification=True):
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    if disable_ssl_verification:
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    si = SmartConnect(host=host, user=user, pwd=pwd, port=443, sslContext=ssl_context)

    atexit.register(Disconnect, si)
    return si

def get_all_hosts(si):
    content = si.RetrieveContent()
    all_hosts = []

    for datacenter in content.rootFolder.childEntity:
        if hasattr(datacenter, 'hostFolder'):
            host_folder = datacenter.hostFolder
            hosts = _recurse_host_folder(host_folder)
            all_hosts.extend(hosts)

    return all_hosts


def get_host_by_name(si, host_names):
    all_hosts = []
    all_hosts.extend(get_all_hosts(si))

    matching_hosts = []
    for host in all_hosts:
        if host.name in host_names:
            matching_hosts.append(host)

    return matching_hosts

def _recurse_host_folder(folder):
    host_list = []
    if hasattr(folder, 'childEntity'):
        for child in folder.childEntity:
            if isinstance(child, vim.ComputeResource) or isinstance(child, vim.ClusterComputeResource):
                host_list.extend(child.host)
            elif isinstance(child, vim.Folder):
                host_list.extend(_recurse_host_folder(child))
    return host_list


def get_perf_counter_key(si, counter_name, counter_type='average'):
    perf_manager = si.content.perfManager
    for c in perf_manager.perfCounter:
        full_name = f'{c.groupInfo.key}.{c.nameInfo.key}.{c.rollupType}'
        if full_name == f'{counter_name}.{counter_type}':
            return c.key
    return None


def build_query_spec(host, metric_id, instance, interval_id=20, samples=10):
    return vim.PerformanceManager.QuerySpec(
        entity=host,
        metricId=[vim.PerformanceManager.MetricId(counterId=metric_id, instance=instance)],
        intervalId=interval_id,
        maxSample=samples
    )

def main():
    password = get_password_from_file(password_file)

    si = get_si_instance(VCENTER_HOST, VCENTER_USER, password)

    hosts = get_all_hosts(si)
    if not hosts:
        print("No hosts found!")
        return

    net_usage_key = get_perf_counter_key(si, "net.usage", "average")
    if net_usage_key is None:
        print("Could not find key!")
        return

    perf_manager = si.content.perfManager

    all_data = {}

    for host in hosts:
        host_name = host.name
        all_data[host_name] = {}

        query_spec = []

        for nic in NIC_LIST:
            spec = build_query_spec(host, net_usage_key, nic, interval_id=20, samples=300)
            query_spec.append(spec)

        results = perf_manager.QueryPerf(query_spec)

        for i, result in enumerate(results):
            nic_name = NIC_LIST[i]
            if result and result.sampleInfo:
                timestamps = [info.timestamp for info in result.sampleInfo]
                if result.value:
                    usage_values = result.value[0].value
                else:
                    usage_values = []
            else:
                timestamps = []
                usage_values = []

            all_data[host_name][nic_name] = {
                'timestamps': timestamps,
                'values': usage_values
            }
    sorted_host_names = sorted(all_data.keys())

    for host_name in sorted_host_names:
        nic_data = all_data[host_name]
        plt.figure(figsize=(7, 4))

        for nic_name in nic_data:
            if nic_name in NIC_LIST:
                if nic_name in nic_data:
                    ts = nic_data[nic_name]['timestamps']
                    vals = nic_data[nic_name]['values']

                    vals_in_MBps = [v / 1000 for v in vals]
                    x = range(len(ts))

                    plt.plot(x, vals_in_MBps, label=f'{nic_name} (MBps)')

        plt.title(f"Netværksforbrug for host: {host_name}")
        plt.xlabel("Seneste målepunkter (20 sek. intervaller)")
        plt.ylabel("Forbrug MB/s")
        plt.legend()

    plt.show()

if __name__ == '__main__':
    main()
