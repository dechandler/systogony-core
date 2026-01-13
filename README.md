# Systogony Core

Systogony is the automation for my personal environment (laptops, servers, routers, appliances, IoT devices, cloud services), and Core is the orchestration and command layer.

It provides input data for automation, coordinates addresses and service locations, and provides a CLI to tie together disparate automation platforms and tooling.

At its core, this turns a blueprint document into calculated system and service parameters.

## Design Goals

- Minimize redundant specifications to ensure an environment change needs only be made in one place in the blueprint

- Provide enough flexibility to specify parameters where they make sense in the document

- Make service instances individually addressable in automation, rather than properties of their host systems

- Control access between systems granularly using network microsegmentation and comprehensive default-deny firewall rules

- Allow in the blueprint to refer to groups of resources by association with other resources (eg, all hosts with instances of a service)

## Structure

The CLI and configuration framework is declib, a common library I wrote to provide a consistent interface for my projects.

Resources defined in the blueprint are internalized as objects, one of: Host, Network, Service, ServiceInstance (connection between a Host and Service), Interface (connection between a Host and Network), Acl (network allow rules between hosts, networks, and services). Each object has implicit connections to each other type of object that are calculated upfront, to ease querying and restructuring the data.

Each resource has a unique identifier, which identifies its resource type and places it in context. Resources can be addressed in the blueprint by a shorthand, which searches resources and resolves to members of the contextually relevant type.
