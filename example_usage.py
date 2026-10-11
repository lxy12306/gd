"""Read-only example. Run after configuring ~/.ossenv: python example_usage.py."""

from oss_toolkit import OSSManager


def main():
    manager = OSSManager()
    for item in manager.list_objects(limit=10):
        print(item.to_dict())
    for item in manager.search("文生图", pattern="*.png", limit=10):
        print("检索结果：", item.to_dict())

    # Use these calls in your own application as needed:
    # manager.upload("./image.png", "images/image.png")
    # manager.download("images/image.png", "./downloads/image.png")
    # manager.upload_directory("./images", "images/")
    # manager.download_directory("images/", "./downloads/images")
    # print(manager.signed_url("images/image.png", expires=600)["url"])


if __name__ == "__main__":
    main()
