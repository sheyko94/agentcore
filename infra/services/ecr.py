from aws_cdk import RemovalPolicy, aws_ecr as ecr, aws_ecr_assets as assets
from cdk_ecr_deployment import DockerImageName, ECRDeployment


def create_chat_repository(stack):
    return ecr.Repository(
        stack, "ChatRepository",
        repository_name="agentcore-chat-cdk",
        removal_policy=RemovalPolicy.DESTROY,
        empty_on_delete=True,
    )


def create_chat_image(stack, chat_directory):
    # CDK first uploads the built image to its bootstrap staging repository.
    return assets.DockerImageAsset(
        stack, "ChatImage", directory=str(chat_directory),
        platform=assets.Platform.LINUX_ARM64,
    )


def publish_chat_image(stack, image, repository, publishing_role):
    image_uri = repository.repository_uri_for_tag(image.asset_hash)
    publication = ECRDeployment(
        stack, "PublishChatImage",
        src=DockerImageName(image.image_uri),
        dest=DockerImageName(image_uri),
        image_arch=["arm64"],
        role=publishing_role.without_policy_updates(),
    )
    publication.node.add_dependency(repository, publishing_role)
    return image_uri, publication
