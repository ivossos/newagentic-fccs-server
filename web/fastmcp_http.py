from fccs_agent.fastmcp_server import build_fastmcp_server


def main() -> None:
    server = build_fastmcp_server()
    server.run("streamable-http")


if __name__ == "__main__":
    main()
