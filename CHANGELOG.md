# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- SmartAdaptiveVideoField with intelligent quality ladder generation
- Progressive video processing with preview-first approach
- Advanced analytics and monitoring API
- GPU acceleration support preparation
- Batch operations for video optimization

## [1.0.0] - 2025-01-XX

### Added
- Initial release of django-hlsfield
- `VideoField` for basic video handling with metadata extraction
- `HLSVideoField` for HTTP Live Streaming with multiple quality levels
- `DASHVideoField` for MPEG-DASH adaptive streaming
- `AdaptiveVideoField` for combined HLS + DASH output
- Automatic preview frame extraction at configurable timestamp
- Support for nested and flat sidecar file layouts
- Celery integration for background video processing
- Storage-agnostic design (works with S3, local files, etc.)
- Ready-to-use HTML5 video players with quality selection
- Comprehensive test suite
- Production-ready configuration examples
- Docker and nginx configuration templates

### Features
- **Automatic Metadata Extraction**: Duration, dimensions, bitrate
- **Preview Generation**: Thumbnail extraction at specified time
- **Multi-Quality Transcoding**: Configurable quality ladders
- **Format Support**: HLS (.m3u8 + .ts), DASH (.mpd + .m4s), MP4
- **Background Processing**: Optional Celery integration
- **Storage Flexibility**: Any Django storage backend
- **Admin Integration**: Custom widgets for video preview
- **Template Tags**: Easy embedding in Django templates

### Supported Versions
- Python: 3.10, 3.11, 3.12, 3.13
- Django: 4.2, 5.0, 5.1
- FFmpeg: 4.4+ (required system dependency)

### Documentation
- Complete README with examples
- API documentation
- Production deployment guide
- Performance optimization tips
- Troubleshooting guide

[Unreleased]: https://github.com/akula993/django-hlsfield/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/akula993/django-hlsfield/releases/tag/v1.0.0
