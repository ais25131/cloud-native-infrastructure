Vagrant.configure("2") do |config|

  config.vm.box = "bento/ubuntu-24.04"

%{ for vm_name, vm_data in vms ~}

  config.vm.define "${vm_name}" do |vm|

    vm.vm.hostname = "${vm_name}"

    vm.vm.network "private_network", ip: "${vm_data.ip}"

    vm.vm.provider "virtualbox" do |vb|
      vb.name   = "${vm_name}"
      vb.memory = ${vm_data.memory}
      vb.cpus   = ${vm_data.cpus}
    end

  end

%{ endfor ~}

end